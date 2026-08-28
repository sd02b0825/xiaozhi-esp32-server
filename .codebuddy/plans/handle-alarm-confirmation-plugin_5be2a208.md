---
name: handle-alarm-confirmation-plugin
overview: 创建告警确认插件 `handle_alarm_confirmation.py`，当用户确认告警时调用 `post_alarm_response` API 然后退出对话，否则直接退出。同时修改 `plugin_executor.py` 支持异步插件函数。
todos:
  - id: create-plugin-file
    content: 新建 handle_alarm_confirm.py 插件文件，实现同步函数、异步桥接 post_alarm_response、退出对话逻辑
    status: completed
  - id: register-necessary-function
    content: 修改 plugin_executor.py，将 handle_alarm_confirm 加入 necessary_functions 列表
    status: completed
    dependencies:
      - create-plugin-file
---

## 用户需求

编写一个新插件 `handle_alarm_confirm`，在告警确认流程中供 LLM 调用：

- 当用户**确认告警**时 → 调用 `post_alarm_response` 接口通知后端 → 退出对话
- 当用户**不确认**时 → 直接退出对话（不调用接口）

## 产品概述

该插件是系统控制类函数（SYSTEM_CTL），由 LLM 在对话中根据用户意图判定后自动调用。它桥接了告警确认逻辑与对话退出逻辑，确保告警结果被正确记录到后端系统。

## 核心功能

- LLM 根据用户语音回复判定 `confirmed` 参数（true/false）
- 确认时异步调用 `post_alarm_response` 接口，传递 session_id、confirmed=true 等信息
- 取消时跳过接口调用，直接退出对话
- 无论接口调用成功或失败，均设置退出标志并返回适当回复
- 防御性检查 `pending_alarm_confirm` 状态是否存在，避免空指针异常

## 技术栈

- 语言：Python（同步函数 + 异步桥接）
- 注册机制：`@register_function` 装饰器，`ToolType.SYSTEM_CTL`
- 异步桥接：`asyncio.run_coroutine_threadsafe` 将异步 `post_alarm_response` 投递到 `conn.loop` 执行
- 返回类型：`ActionResponse(action=Action.RESPONSE, result=..., response=...)`

## 实现方案

### 核心策略

完全对齐项目现有的插件模式（`handle_exit_intent.py` + `hass_play_music.py`），复用 `asyncio.run_coroutine_threadsafe` 桥接模式解决同步插件函数无法直接 `await` 异步函数的限制。

### 数据流

```mermaid
sequenceDiagram
    participant User as 用户
    participant ASR as 语音识别
    participant LLM as 大模型
    participant Plugin as handle_alarm_confirm
    participant API as post_alarm_response
    participant Conn as ConnectionHandler

    Note over User,Conn: 前置：handle_alarm_inquiry_detect 已设置 pending_alarm_confirm

    User->>ASR: 语音回复（如"好的通知吧"）
    ASR->>LLM: 转写文本
    LLM->>LLM: 判定 confirmed=true
    LLM->>Plugin: 调用 handle_alarm_confirm(confirmed=true)
    
    alt confirmed=true 且 pending 存在
        Plugin->>Conn: asyncio.run_coroutine_threadsafe
        Conn->>API: POST /alarm/response
        API-->>Conn: 返回结果
        Plugin->>Conn: close_after_chat = True
        Plugin-->>LLM: "好的，已经帮您通知家人了"
    else confirmed=false 或无 pending
        Plugin->>Conn: close_after_chat = True
        Plugin-->>LLM: "好的，那我就不打扰了"
    end
    Conn->>Conn: 对话结束，关闭连接
```

### 关键实现细节

1. **异步桥接**：由于 `plugin_executor.py` 第 33 行 `result = func_item.func(conn, **arguments)` 为同步调用（不 await），插件函数必须是同步的。参考 `hass_play_music.py` 的模式，使用：

```python
future = asyncio.run_coroutine_threadsafe(
post_alarm_response(api_base_url, session_id, True, text),
conn.loop
)
```

2. **防御性设计**：函数始终注册为必要函数（加入 `necessary_functions`），但内部先检查 `conn.pending_alarm_confirm` 是否存在、是否有效，避免在没有告警上下文时误操作。

3. **退出保证**：无论 `post_alarm_response` 调用成功还是失败，均在 `finally` 或异常处理后设置 `conn.close_after_chat = True` 并清理 `pending_alarm_confirm`。

4. **复用现有常量**：引用 `alarmConfirmHandler.py` 中的 `DEFAULT_CONFIRM_REPLY` 和 `DEFAULT_CANCEL_REPLY` 作为默认回复文案。

## 目录结构

```
main/xiaozhi-server/
├── plugins_func/functions/
│   └── handle_alarm_confirm.py          # [NEW] 告警确认插件。实现 handle_alarm_confirm 同步函数：
│                                           - 接收 conn 和 confirmed(bool) 参数
│                                           - conconfirmed=true 时通过 asyncio.run_coroutine_threadsafe 
│                                             桥接调用 post_alarm_response 异步接口
│                                           - 设置 conn.close_after_chat = True 退出对话
│                                           - 返回 ActionResponse 含适当回复文案
│                                           - 完整的异常捕获与日志记录
├── core/providers/tools/server_plugins/
│   └── plugin_executor.py              # [MODIFY] line 57，在 necessary_functions 列表中加入
│                                          "handle_alarm_confirm"，确保函数始终可用
└── core/handle/
    └── alarmConfirmHandler.py          # [REFERENCE] 引用其中的 post_alarm_response、
                                           DEFAULT_CONFIRM_REPLY、DEFAULT_CANCEL_REPLY
```

## 代理扩展

无需使用任何扩展。本任务为纯代码实现，不涉及外部工具、浏览器自动化或技能系统。