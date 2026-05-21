"""统一工具管理器"""

import json
from typing import Dict, List, Optional, Any
from config.manage_api_client import get_family_members_by_device
from config.logger import setup_logging
from plugins_func.register import Action, ActionResponse
from .base import ToolType, ToolDefinition, ToolExecutor


class ToolManager:
    """统一工具管理器，管理所有类型的工具"""

    def __init__(self, conn):
        self.conn = conn
        self.logger = setup_logging()
        self.executors: Dict[ToolType, ToolExecutor] = {}
        self._cached_tools: Optional[Dict[str, ToolDefinition]] = None
        self._cached_function_descriptions: Optional[List[Dict[str, Any]]] = None

    def register_executor(self, tool_type: ToolType, executor: ToolExecutor):
        """注册工具执行器"""
        self.executors[tool_type] = executor
        self._invalidate_cache()
        self.logger.debug(f"注册工具执行器: {tool_type.value}")

    def _invalidate_cache(self):
        """使缓存失效"""
        self._cached_tools = None
        self._cached_function_descriptions = None

    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """获取所有工具定义"""
        if self._cached_tools is not None:
            return self._cached_tools

        all_tools = {}
        for tool_type, executor in self.executors.items():
            try:
                tools = executor.get_tools()
                for name, definition in tools.items():
                    if name in all_tools:
                        self.logger.warning(f"工具名称冲突: {name}")
                    all_tools[name] = definition
            except Exception as e:
                self.logger.error(f"获取{tool_type.value}工具时出错: {e}")

        self._cached_tools = all_tools
        return all_tools

    def get_function_descriptions(self) -> List[Dict[str, Any]]:
        """获取所有工具的函数描述（OpenAI格式）"""
        if self._cached_function_descriptions is not None:
            return self._cached_function_descriptions

        descriptions = []
        tools = self.get_all_tools()
        for tool_definition in tools.values():
            descriptions.append(tool_definition.description)

        self._cached_function_descriptions = descriptions
        return descriptions

    def has_tool(self, tool_name: str) -> bool:
        """检查是否存在指定工具"""
        tools = self.get_all_tools()
        return tool_name in tools

    def get_tool_type(self, tool_name: str) -> Optional[ToolType]:
        """获取工具类型"""
        tools = self.get_all_tools()
        tool_def = tools.get(tool_name)
        return tool_def.tool_type if tool_def else None

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ActionResponse:
        """执行工具调用"""
        try:
            # 查找工具类型
            tool_type = self.get_tool_type(tool_name)
            if not tool_type:
                return ActionResponse(
                    action=Action.NOTFOUND,
                    response=f"工具 {tool_name} 不存在",
                )

            # 获取对应的执行器
            executor = self.executors.get(tool_type)
            if not executor:
                return ActionResponse(
                    action=Action.ERROR,
                    response=f"工具类型 {tool_type.value} 的执行器未注册",
                )

            guarded_response = await self._guard_send_message(tool_name, arguments, tool_type)
            if guarded_response is not None:
                return guarded_response

            # 执行工具
            self.logger.info(f"执行工具: {tool_name}，参数: {arguments}")
            result = await executor.execute(self.conn, tool_name, arguments)
            self.logger.debug(f"工具执行结果: {result}")
            return result

        except Exception as e:
            self.logger.error(f"执行工具 {tool_name} 时出错: {e}")
            return ActionResponse(action=Action.ERROR, response=str(e))

    async def _guard_send_message(
        self, tool_name: str, arguments: Dict[str, Any], tool_type: ToolType
    ) -> Optional[ActionResponse]:
        """发送消息前置亲属匹配校验。"""
        actual_tool_name = tool_name[4:] if tool_name.startswith("mcp_") else tool_name
        if actual_tool_name != "send_message" or tool_type != ToolType.SERVER_MCP:
            return None

        receiver = arguments.get("receiver")
        device_id = arguments.get("device_id") or getattr(self.conn, "device_id", None)
        if not receiver or not device_id:
            return None

        confirmed = self._is_send_message_family_checked(arguments)
        try:
            family_members = await get_family_members_by_device(device_id)
        except Exception as e:
            self.logger.warning(f"发送消息亲属列表查询失败，继续调用原工具: {e}")
            return None
        if family_members is None:
            self.logger.warning("发送消息亲属列表不可用，继续调用原工具")
            return None

        if not family_members:
            return ActionResponse(
                action=Action.RESPONSE,
                response="我还没有找到你的亲属列表，请先在 APP 里添加亲属。",
            )

        exact_member = self._find_exact_family_member(receiver, family_members)
        if exact_member is not None:
            canonical_name = exact_member.get("name")
            if canonical_name:
                arguments["receiver"] = canonical_name
            self._strip_send_message_internal_args(arguments)
            self.logger.info(f"发送消息亲属精确命中: receiver={receiver}")
            return None

        if confirmed:
            self._strip_send_message_internal_args(arguments)
            return ActionResponse(
                action=Action.RESPONSE,
                response="我还不能确定要发给哪位亲属，请说出亲属列表里的准确姓名。",
            )

        if getattr(self.conn, "intent_type", None) != "function_call":
            candidate_names = self._format_family_member_names(family_members)
            return ActionResponse(
                action=Action.RESPONSE,
                response=(
                    f"我没能精确匹配到{receiver}。当前可选亲属有：{candidate_names}，"
                    "请说出要发送的准确姓名。"
                ),
            )

        family_context = self._build_family_member_context(receiver, family_members)
        self.logger.info(f"发送消息交由智能体判断亲属候选: receiver={receiver}")
        return ActionResponse(action=Action.REQLLM, result=family_context)

    def _find_exact_family_member(
        self, receiver: str, family_members: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        receiver_name = self._normalize_family_name(receiver)
        for member in family_members:
            member_name = self._normalize_family_name(member.get("name"))
            remark = self._normalize_family_name(member.get("remark"))
            if receiver_name and receiver_name in {member_name, remark}:
                return member
        return None

    def _build_family_member_context(
        self, receiver: str, family_members: List[Dict[str, Any]]
    ) -> str:
        safe_members = [
            {
                "id": member.get("id"),
                "name": member.get("name"),
                "remark": member.get("remark"),
            }
            for member in family_members
        ]
        return json.dumps(
            {
                "type": "send_message_family_member_check",
                "receiverFromAsr": receiver,
                "familyMembers": safe_members,
                "instruction": (
                    "你正在处理给亲属发送消息的工具调用。请只在 familyMembers 候选范围内判断 "
                    "receiverFromAsr 是否可能是某个亲属的同音、近音、昵称或误识别结果。"
                    "如果能确定是唯一亲属，不要向用户确认，必须立即再次调用 send_message。"
                    "再次调用时 receiver 必须使用 familyMembers 中该亲属的标准 name，"
                    "禁止继续使用 receiverFromAsr，并且必须携带 family_member_checked=true。"
                    "如果无法确定唯一亲属，或有多个可能候选，请让用户选择。"
                    "如果没有候选，请提示用户未找到亲属。"
                    "不要使用 familyMembers 之外的联系人，也不要臆造联系人。"
                ),
            },
            ensure_ascii=False,
        )

    def _normalize_family_name(self, value: Any) -> str:
        if value is None:
            return ""
        return "".join(str(value).split())

    def _is_send_message_family_checked(self, arguments: Dict[str, Any]) -> bool:
        return bool(
            arguments.get("family_member_checked")
            or arguments.get("receiverConfirmed")
            or arguments.get("receiver_confirmed")
        )

    def _strip_send_message_internal_args(self, arguments: Dict[str, Any]):
        for key in (
            "family_member_checked",
            "receiverConfirmed",
            "receiver_confirmed",
        ):
            arguments.pop(key, None)

    def _format_family_member_names(self, family_members: List[Dict[str, Any]]) -> str:
        names = [str(member.get("name")) for member in family_members if member.get("name")]
        return "、".join(names) if names else "暂无可用亲属"

    def get_supported_tool_names(self) -> List[str]:
        """获取所有支持的工具名称"""
        tools = self.get_all_tools()
        return list(tools.keys())

    def refresh_tools(self):
        """刷新工具缓存"""
        self._invalidate_cache()
        self.logger.debug("工具缓存已刷新")

    def get_tool_statistics(self) -> Dict[str, int]:
        """获取工具统计信息"""
        stats = {}
        for tool_type, executor in self.executors.items():
            try:
                tools = executor.get_tools()
                stats[tool_type.value] = len(tools)
            except Exception as e:
                self.logger.error(f"获取{tool_type.value}工具统计时出错: {e}")
                stats[tool_type.value] = 0
        return stats
