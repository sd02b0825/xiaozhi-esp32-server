#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@time: 2026/01/08
@file: powermem.py
@desc: PowerMem memory provider for xiaozhi-esp32-server
       PowerMem is an open-source agent memory component from OceanBase
       GitHub: https://github.com/oceanbase/powermem
       Website: https://www.powermem.ai/
@Author: wayyoungboy
"""

import asyncio
import collections
import json
import time
import traceback
from typing import Optional, Dict, Any

from ..base import MemoryProviderBase, logger

TAG = __name__


class MemoryProvider(MemoryProviderBase):
    """
    PowerMem memory provider implementation.

    PowerMem (https://www.powermem.ai/) is an open-source intelligent memory engine from OceanBase,
    providing hybrid retrieval (vector + full-text + knowledge graph), Ebbinghaus forgetting curve,
    and smart memory extraction for AI agents.

    Two modes:
        - AsyncMemory (enable_user_profile=False): Pure conversation memory with semantic retrieval.
        - UserMemory (enable_user_profile=True): Memory + structured user profile auto-extraction.

    Storage backends:
        - oceanbase (recommended, best performance)
        - seekdb (recommended, AI-native storage)
        - sqlite (lightweight, for resource-constrained environments)
        - postgres

    LLM providers: qwen, openai, zhipu (glm-4-flash is free), etc.
    Embedding providers: qwen, openai, etc.

    Key design: infer=False is used for add() to disable SDK's UPDATE/DELETE reasoning,
    preventing LLM from incorrectly overwriting or deleting historical memories due to
    context-switching in bot conversations. Forgetting is handled by PowerMem's built-in
    Ebbinghaus curve (time/frequency-based decay) instead.

    NaN resilience: PowerMem server occasionally returns "json: unsupported value: NaN"
    errors on batch add(). The provider auto-retries once and falls back to per-message
    saving, skipping entries that trigger NaN, keeping the conversation flow intact.

    Session-level caching: search results are cached per user_id with a configurable TTL
    (memory_cache_ttl, default 60s). This avoids redundant PowerMem search() calls when
    the same user queries memory multiple times within a short window. The cache is
    invalidated on save_memory() to ensure freshness after new messages are stored.
    User profile has a separate TTL cache (profile_cache_ttl, default 300s).
    After save_memory(), the cache is refreshed from add() return value when available.

    Config options:
        - enable_user_profile: bool - Enable UserMemory for user profiling (supports oceanbase, seekdb, sqlite)
        - database_provider: str - Storage backend (sqlite, oceanbase, seekdb, postgres)
        - llm_provider: str - LLM provider (qwen, openai, zhipu, etc.)
        - embedding_provider: str - Embedding provider (qwen, openai, etc.)
        - memory_cache_ttl: int - Search result cache TTL in seconds (default 60, 0 to disable)
        - profile_cache_ttl: int - User profile cache TTL in seconds (default 300, 0 to disable)
        - search_limit: int - Number of search results to return (default 15)
        - max_cache_size: int - Max cache entries per cache dict (default 1000, 0 = unlimited)
        - nan_retry_count: int - NaN error retry count (default 1, 0 = no retry)
        - nan_retry_delay: float - NaN retry base delay in seconds (default 1.0)
    """

    def __init__(self, config: Dict[str, Any], summary_memory: Optional[str] = None):
        super().__init__(config)
        self.use_powermem = False
        self.memory_client = None
        self.enable_user_profile = False

        # ---- 配置校验前置化 ----
        if not isinstance(config, dict):
            raise ValueError(f"PowerMem config must be a dict, got {type(config).__name__}")

        # 校验 provider 拼写（仅检查已知值，未知值交给 SDK 校验）
        valid_database_providers = {"sqlite", "oceanbase", "seekdb", "postgres"}
        valid_llm_providers = {"qwen", "openai", "zhipu"}
        valid_embedding_providers = {"qwen", "openai", "ollama"}

        db_provider = config.get("database_provider", "sqlite")
        llm_provider = config.get("llm_provider", "qwen")
        emb_provider = config.get("embedding_provider", "qwen")

        if db_provider not in valid_database_providers:
            logger.bind(tag=TAG).warning(
                f"[PowerMem配置] 未知 database_provider='{db_provider}'，"
                f"有效值: {valid_database_providers}，继续尝试初始化"
            )
        if llm_provider not in valid_llm_providers:
            logger.bind(tag=TAG).warning(
                f"[PowerMem配置] 未知 llm_provider='{llm_provider}'，"
                f"有效值: {valid_llm_providers}，继续尝试初始化"
            )
        if emb_provider not in valid_embedding_providers:
            logger.bind(tag=TAG).warning(
                f"[PowerMem配置] 未知 embedding_provider='{emb_provider}'，"
                f"有效值: {valid_embedding_providers}，继续尝试初始化"
            )

        # ---- 缓存配置 ----
        self._profile_cache_ttl = config.get("profile_cache_ttl", 300)
        # 结构: Dict[user_id, (profile_text, expire_time)]
        self._profile_cache = collections.OrderedDict()

        # 会话级搜索结果缓存，避免同一轮对话中重复调用 PowerMem search()
        # 结构: Dict[user_id, (cached_result, expire_time)]
        # 默认 TTL 300s（5分钟），可通过 memory_cache_ttl 配置；设为 0 则禁用缓存
        self._search_cache = collections.OrderedDict()
        self._search_cache_ttl = config.get("memory_cache_ttl", 300)

        # 缓存容量上限，默认 1000 条，0 = 无限制
        self._max_cache_size = config.get("max_cache_size", 1000)

        # 记忆搜索返回条数，默认 15 条（减少数据库查询压力）
        self._search_limit = config.get("search_limit", 15)

        # NaN 错误重试配置（_sanitize_messages 已从源头清洗 NaN，重试作为兜底）
        self._nan_retry_count = config.get("nan_retry_count", 0)   # 默认不重试，直接降级逐条保存
        self._nan_retry_delay = config.get("nan_retry_delay", 0.1) # 重试等待间隔

        # 后台画像刷新任务跟踪，避免同一 user_id 启动多个重复的后台刷新
        # 结构: Dict[user_id, asyncio.Task]
        self._profile_refresh_tasks = {}

        # 用户画像提取约束：只提取以下字段
        self.profile_schema = {
            "用户名": "",
            "出生日期": "", 
            "性别": "",
            "对智能体称呼": "",
            "食物偏好": "",
            "运动偏好": "",
            "音乐": "",
            "兴趣爱好": "",
            "家庭成员": "",
        }
        self._profile_prompt = (
            "你是一个用户画像提取助手。从用户的对话中提取个人画像信息。"
            "只提取以下9个字段，每个字段用一行表示，格式为「字段名：值」。"
            "如果没有相关信息则留空，不要编造。\n"
            "字段列表：\n"
            "- 用户名：对话中如何称呼用户\n"
            "- 出生日期：用户出生日期\n"
            "- 性别：用户的性别\n"
            "- 对智能体称呼：对话中用户怎么称呼智能体\n"
            "- 食物偏好：用户的食物偏好\n"
            "- 运动偏好：用户的运动偏好\n"
            "- 音乐：用户的音乐偏好\n"
            "- 兴趣爱好：用户的兴趣爱好\n"
            "- 家庭成员：用户的家庭成员\n"
            "\n请基于新的对话内容增量更新画像，只修改有变化的字段，保持已有信息不变。"
        )

        try:
            # Check if user profile mode is enabled
            # 用户画像功能支持: oceanbase、seekdb、sqlite (powermem 0.3.0+)
            self.enable_user_profile = config.get("enable_user_profile", False)
            
            # Get configuration parameters
            database_provider = config.get("database_provider", "sqlite")
            llm_provider = config.get("llm_provider", "qwen")
            embedding_provider = config.get("embedding_provider", "qwen")

            # Build powermem configuration dict
            # PowerMem supports two config styles:
            # 1. powermem style: database, llm, embedding
            # 2. mem0 style: vector_store, llm, embedder
            powermem_config = {}

            # Configure vector store / database
            if "vector_store" in config:
                powermem_config["vector_store"] = config["vector_store"]
            elif "database" in config:
                # PowerMem SDK 也支持 "database" 键的旧风格配置
                # 同时设置 vector_store 用于后续日志记录的兼容读取
                powermem_config["database"] = config["database"]
                database_cfg = config["database"]
                powermem_config["vector_store"] = {
                    "provider": database_cfg.get("provider", database_provider) if isinstance(database_cfg, dict) else database_provider,
                    "config": database_cfg.get("config", {}) if isinstance(database_cfg, dict) else {}
                }
            else:
                powermem_config["vector_store"] = {
                    "provider": database_provider,
                    "config": {}
                }

            # Configure LLM
            if "llm" in config:
                powermem_config["llm"] = config["llm"]
            else:
                llm_config = {}
                if "llm_api_key" in config:
                    llm_config["api_key"] = config["llm_api_key"]
                if "llm_model" in config:
                    llm_config["model"] = config["llm_model"]
                # Handle base_url based on provider type
                # - qwen provider uses dashscope_base_url
                # - openai/other providers use openai_base_url
                # NOTE: Skip empty strings to avoid Pydantic extra_forbidden errors (Issue #3053)
                if "llm_base_url" in config and config["llm_base_url"]:
                    if llm_provider == "qwen":
                        llm_config["dashscope_base_url"] = config["llm_base_url"]
                    else:
                        llm_config["openai_base_url"] = config["llm_base_url"]
                if "openai_base_url" in config and config["openai_base_url"]:
                    llm_config["openai_base_url"] = config["openai_base_url"]
                if "dashscope_base_url" in config and config["dashscope_base_url"]:
                    llm_config["dashscope_base_url"] = config["dashscope_base_url"]
                powermem_config["llm"] = {
                    "provider": llm_provider,
                    "config": llm_config
                }

            # Configure embedder
            if "embedder" in config:
                powermem_config["embedder"] = config["embedder"]
            else:
                embedder_config = {}
                if "embedding_api_key" in config:
                    embedder_config["api_key"] = config["embedding_api_key"]
                if "embedding_model" in config:
                    embedder_config["model"] = config["embedding_model"]
                if "embedding_dims" in config:
                    embedder_config["embedding_dims"] = config["embedding_dims"]
                # Handle base_url based on provider type
                # - qwen provider uses dashscope_base_url
                # - openai/other providers use openai_base_url
                # Priority: embedding_xxx_base_url > embedding_base_url > xxx_base_url
                # NOTE: Skip empty strings to avoid Pydantic extra_forbidden errors (Issue #3053)
                if "embedding_base_url" in config and config["embedding_base_url"]:
                    if embedding_provider == "qwen":
                        embedder_config["dashscope_base_url"] = config["embedding_base_url"]
                    else:
                        embedder_config["openai_base_url"] = config["embedding_base_url"]
                # Embedding-specific base_url (higher priority)
                if "embedding_openai_base_url" in config and config["embedding_openai_base_url"]:
                    embedder_config["openai_base_url"] = config["embedding_openai_base_url"]
                if "embedding_dashscope_base_url" in config and config["embedding_dashscope_base_url"]:
                    embedder_config["dashscope_base_url"] = config["embedding_dashscope_base_url"]
                powermem_config["embedder"] = {
                    "provider": embedding_provider,
                    "config": embedder_config
                }
            # 打印powermem配置
            # logger.bind(tag=TAG).info(f"PowerMem config: {powermem_config}")

            # 注入用户画像提取约束
            powermem_config["profile_prompt"] = self._profile_prompt

            # Initialize memory client based on mode
            if self.enable_user_profile:
                # UserMemory: 同步接口，支持用户画像自动提取，需通过 asyncio.to_thread 包裹调用
                from powermem import UserMemory
                self.memory_client = UserMemory(config=powermem_config)
                memory_mode = "UserMemory (用户画像模式)"
            else:
                # AsyncMemory: 全异步接口，纯对话记忆存储与检索，不支持用户画像
                from powermem import AsyncMemory
                self.memory_client = AsyncMemory(config=powermem_config)
                memory_mode = "AsyncMemory (普通记忆模式)"

            self.use_powermem = True

            logger.bind(tag=TAG).info(
                f"PowerMem initialized successfully: mode={memory_mode}, "
                f"database={powermem_config['vector_store']['provider']}, llm={powermem_config['llm']['provider']}, embedding={powermem_config['embedder']['provider']}"
            )            
            
        except ImportError as e:
            logger.bind(tag=TAG).error(
                f"PowerMem not installed. Please install with: pip install powermem. Error: {e}"
            )
            self.use_powermem = False
        except Exception as e:
            logger.bind(tag=TAG).error(f"Failed to initialize PowerMem: {str(e)}")
            logger.bind(tag=TAG).debug(f"Detailed error: {traceback.format_exc()}")
            self.use_powermem = False

    @staticmethod
    def _extract_speaker_from_query(query: str) -> str:
        """从 ASR JSON query 中提取 speaker 字段（声纹识别后的说话人姓名）。"""
        if not query:
            return ""
        try:
            if query.strip().startswith("{") and query.strip().endswith("}"):
                data = json.loads(query)
                speaker = data.get("speaker")
                if speaker and str(speaker).strip():
                    return str(speaker).strip()
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return ""

    @classmethod
    def _resolve_user_id(cls, user_id: str, query: str = None) -> str:
        """将 user_id 归一化为 {device_id}:{姓名} 格式。

        新格式：{device_id}:{姓名}，同设备同名说话人共享记忆（支持一人多声纹）。
        兼容旧格式 {device_id}:person:{profile_id}：从 query JSON 的 speaker 字段重建。
        """
        if not user_id:
            return user_id

        if ":person:" not in user_id:
            return user_id

        speaker = cls._extract_speaker_from_query(query or "")
        if not speaker:
            return user_id

        device_id = user_id.split(":person:", 1)[0]
        return f"{device_id}:{speaker}"

    @staticmethod
    def _extract_text_from_content(content: str) -> str:
        """从消息内容中提取纯文本。

        如果 content 是 JSON 格式（ASR 带说话人/情绪标签），提取 "content" 字段；
        否则返回原始 content。

        Args:
            content: 原始消息内容

        Returns:
            提取后的纯文本内容
        """
        if not content:
            return content
        try:
            if content.strip().startswith("{") and content.strip().endswith("}"):
                data = json.loads(content)
                if "content" in data:
                    return data["content"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return content

    @staticmethod
    def _parse_profile_result(profile_result: Dict[str, Any]) -> str:
        """将 PowerMem profile() / add() 返回的画像结构解析为可读文本。"""
        if not profile_result:
            return ""

        profile_text = ""
        topics = profile_result.get("topics")
        if topics and isinstance(topics, dict):
            parts = []
            for key, value in topics.items():
                if value:
                    parts.append(f"{key}：{value}")
            if parts:
                profile_text = "\n".join(parts)

        if not profile_text:
            profile_text = profile_result.get("profile_content", "") or ""

        return profile_text

    def _build_profile_extraction_prompt(self, existing_profile: str) -> str:
        """构建画像提取 prompt，将已有画像注入供 LLM 增量合并。"""
        if not existing_profile:
            return self._profile_prompt

        return (
            f"{self._profile_prompt}\n\n"
            "【当前已有画像】\n"
            f"{existing_profile}\n\n"
            "重要：请基于【当前已有画像】和【新对话内容】做增量合并。"
            "必须完整保留已有画像中未被新对话明确推翻的信息，"
            "仅补充或更新新对话中明确提到的字段。"
            "禁止丢弃已有信息，禁止仅根据新对话重新生成画像。"
        )

    def _invalidate_profile_cache(self, user_id: str):
        """清除指定用户的画像 TTL 缓存。"""
        if user_id in self._profile_cache:
            del self._profile_cache[user_id]
            logger.bind(tag=TAG).debug(
                f"[用户画像] 清除画像缓存, user_id={user_id}"
            )

    def _update_profile_cache_from_result(self, user_id: str, result: Any):
        """保存成功后用 add() 返回的新画像回填缓存，供逐条保存时下一轮合并使用。"""
        if not isinstance(result, dict):
            self._invalidate_profile_cache(user_id)
            return

        profile_text = self._parse_profile_result(result)
        if profile_text:
            self._profile_cache[user_id] = (
                profile_text,
                time.time() + self._profile_cache_ttl,
            )
            self._evict_if_needed(self._profile_cache)
            logger.bind(tag=TAG).debug(
                f"[用户画像] 保存后回填缓存, user_id={user_id}, "
                f"画像前100字={profile_text[:100]}"
            )
        else:
            self._invalidate_profile_cache(user_id)

    async def _call_add(self, messages, user_id):
        """调用 memory_client.add()，统一处理同步/异步返回值。

        画像提取说明：
        当 enable_user_profile=True 时，UserMemory.add() 每次都会自动触发行人画像的增量提取。
        必须明确指定 profile_type 使其与配置的 profile_prompt 匹配，否则 LLM 可能返回空值覆盖已有画像。

        画像覆盖保护：
        PowerMem 的 add() 在 profile_type="content" 模式下，会用 LLM 从新消息中提取的画像
        全量替换数据库中的旧画像。如果旧画像中的信息（如年龄、工作状态、食物偏好等）在
        新消息中未提及，这些信息就会丢失。

        修复方案：在调用 add() 前先获取已有画像，通过 add(prompt=...) 注入运行时 prompt，
        让 LLM 同时参考"旧画像 + 新消息"做真正的增量合并，而非仅凭新消息重新提取。
        """
        add_kwargs = {
            "messages": messages,
            "user_id": user_id,
            "infer": False,
        }

        if self.enable_user_profile:
            add_kwargs["profile_type"] = "content"

            # 保存前读取已有画像，注入运行时 prompt 防止全量覆盖
            existing_profile = await self.get_user_profile(user_id=user_id)
            add_kwargs["prompt"] = self._build_profile_extraction_prompt(existing_profile)
            if existing_profile:
                logger.bind(tag=TAG).info(
                    f"[用户画像] 保存前注入已有画像, user_id={user_id}, "
                    f"已有画像前100字={existing_profile[:100]}"
                )

        result = self.memory_client.add(**add_kwargs)
        if asyncio.iscoroutine(result):
            result = await result

        if self.enable_user_profile:
            self._update_profile_cache_from_result(user_id, result)

        return result

    @staticmethod
    def _is_nan_error(e: Exception) -> bool:
        """判断异常是否由 PowerMem 服务端 NaN 序列化错误引起。"""
        err_str = str(e)
        return "NaN" in err_str or "unsupported value" in err_str

    @staticmethod
    def _sanitize_messages(messages):
        """清洗消息中的 NaN/Inf 值，避免 PowerMem 服务端 Go json.Marshal 序列化错误。

        PowerMem 服务端使用 Go 实现，json.Marshal 无法序列化 NaN/Inf 浮点值，
        会返回 "json: unsupported value: NaN" 错误。在调用 add() 前提前清洗。
        """
        import math
        sanitized = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, float):
                if math.isnan(content) or math.isinf(content):
                    content = ""
            elif content is None:
                content = ""
            elif isinstance(content, str):
                # 检查字符串中是否包含 NaN 文本（极少数情况）
                if content in ("NaN", "Infinity", "-Infinity"):
                    content = ""
            sanitized.append({"role": msg["role"], "content": content})
        return sanitized

    async def _add_with_retry(self, messages, user_id):
        """
        调用 add()，遇到 NaN 序列化错误时重试并降级为逐条保存。

        PowerMem 服务端处理批量 add() 时偶发 json: unsupported value: NaN 错误
        （Go json.Marshal 无法序列化 NaN 浮点值），重试仍失败则
        降级为逐条保存，跳过有问题的单条消息。

        重试策略：指数退避 delay * (2 ^ retry_num)，默认 delay=1s，最多重试 1 次。
        可通过 nan_retry_count 和 nan_retry_delay 配置。
        """
        # 提前清洗 NaN/Inf 值，从源头避免服务端序列化错误
        messages = self._sanitize_messages(messages)

        last_exception = None
        for attempt in range(self._nan_retry_count + 1):
            try:
                return await self._call_add(messages, user_id)
            except Exception as e:
                if not self._is_nan_error(e):
                    raise
                last_exception = e
                if attempt < self._nan_retry_count:
                    delay = self._nan_retry_delay * (2 ** attempt)
                    logger.bind(tag=TAG).warning(
                        f"[PowerMem保存] NaN错误(第{attempt + 1}次)，{delay}s后重试, user_id={user_id}"
                    )
                    await asyncio.sleep(delay)

        # 所有重试均失败且消息数 > 1：降级为逐条保存
        if len(messages) > 1:
            logger.bind(tag=TAG).warning(
                f"[PowerMem保存] 批量NaN错误(重试{self._nan_retry_count}次后)，降级为逐条保存, user_id={user_id}, 消息数={len(messages)}"
            )
            return await self._add_one_by_one(messages, user_id)

        raise last_exception

    async def _add_one_by_one(self, messages, user_id):
        """逐条保存消息，遇到 NaN 错误的单条跳过，其余继续。"""
        success = 0
        for msg in messages:
            try:
                await self._call_add([msg], user_id)
                success += 1
            except Exception as e:
                tag = "NaN" if self._is_nan_error(e) else "其他"
                logger.bind(tag=TAG).warning(
                    f"[PowerMem保存] 单条跳过({tag}), user_id={user_id}, "
                    f"内容前50字={msg['content'][:50]}, error={str(e)[:80]}"
                )
        logger.bind(tag=TAG).info(
            f"[PowerMem保存] 逐条保存完成, user_id={user_id}, 成功={success}/{len(messages)}"
        )
        return {"saved": success, "total": len(messages)}

    async def save_memory(self, msgs, session_id=None, user_id=None):
        """
        Save conversation messages to PowerMem.

        只保存属于当前 user_id 说话人的 user 消息，避免跨人归因。
        通过 Message 对象上的 memory_user_id 字段判断消息归属。
        user_id 格式为 {device_id}:{姓名}，同设备同名说话人共享记忆空间。

        PowerMem 服务端偶发 NaN 序列化错误（json: unsupported value: NaN），
        内部自动重试 + 降级为逐条保存，对外层调用者透明。

        Args:
            msgs: List of message objects with 'role', 'content' and optional 'memory_user_id' attributes
            session_id: Session identifier (optional, for compatibility)
            user_id: PowerMem user_id for isolation (defaults to self.role_id)

        Returns:
            Result from PowerMem API or None if failed
        """
        if not self.use_powermem or self.memory_client is None:
            logger.bind(tag=TAG).warning("[PowerMem保存] PowerMem不可用，跳过save_memory")
            return None

        if len(msgs) < 2:
            logger.bind(tag=TAG).debug("[PowerMem保存] 消息不足2条，跳过保存")
            return None

        user_id = user_id or self.role_id
        if not user_id:
            logger.bind(tag=TAG).warning(f"[PowerMem保存] user_id为空(self.role_id={self.role_id})，跳过save_memory")
            return None

        # 声纹记忆按 {device_id}:{姓名} 隔离，兼容旧 :person: 格式
        user_id = self._resolve_user_id(user_id)

        # 在 try 外部初始化，确保 except 块可以安全引用
        messages = []
        try:
            skipped_mismatch = 0
            skipped_exclude = 0

            for message in msgs:
                if message.role != "user":
                    continue

                # 跳过标记为排除记忆的消息（如告别提示语、系统限制提示等非用户意图内容）
                if getattr(message, 'exclude_from_memory', False):
                    skipped_exclude += 1
                    continue

                # 通过 Message 上的 memory_user_id 判断消息归属
                # 只保存属于当前 user_id 的消息，跳过其他说话人的消息
                msg_muid = getattr(message, 'memory_user_id', None)
                if msg_muid:
                    msg_muid = self._resolve_user_id(msg_muid, getattr(message, 'content', None))
                if msg_muid and msg_muid != user_id:
                    skipped_mismatch += 1
                    continue

                content = message.content

                # 从 JSON 格式中提取纯文本内容（ASR 带说话人/情绪标签时为 JSON）
                text = self._extract_text_from_content(content)

                messages.append({"role": message.role, "content": text})

            if len(messages) < 1:
                logger.bind(tag=TAG).info(
                    f"[PowerMem保存] 过滤后无有效消息, user_id={user_id}, "
                    f"跳过说话人不匹配={skipped_mismatch}, 跳过排除记忆={skipped_exclude}"
                )
                return None

            logger.bind(tag=TAG).info(
                f'[PowerMem保存] user_id={user_id}, 有效消息数={len(messages)}, '
                f'跳过说话人不匹配={skipped_mismatch}, 跳过排除记忆={skipped_exclude}, '
                f'前3条摘要: {[(m["role"], m["content"][:50]) for m in messages[:3]]}'
            )

            # Add memory using PowerMem SDK
            # infer=False: 禁止 SDK 内部的事实抽取推理（UPDATE/DELETE 操作）
            #   - PowerMem 的 infer 机制会令 LLM 自动判断新消息与已有记忆的关系
            #   - infer=True 时可能执行 UPDATE（更新冲突记忆）或 DELETE（删除过时记忆）
            #   - 在机器人对话场景中，上下文频繁切换容易导致 LLM 误判冲突
            #   - 因此设为 False，只保留新增（ADD）行为，遗忘交由底层的艾宾浩斯遗忘曲线处理
            # retry: PowerMem 服务端偶发 NaN 序列化错误，自动重试并降级为逐条保存
            result = await self._add_with_retry(messages, user_id)

            logger.bind(tag=TAG).info(f"[PowerMem保存] 保存成功, user_id={user_id}, result={str(result)[:200] if result else 'None'}")

            # 保存成功后清除相关缓存
            # 1. 画像缓存：_call_add 已根据 add() 返回值回填或清除，无需在此重复处理
            # 2. 搜索缓存：新消息可能影响后续搜索结果的相关性，需要清除

            # 清除搜索结果缓存，因为新消息可能影响后续搜索结果的相关性
            self._invalidate_search_cache(user_id)

            return result

        except Exception as e:
            msg_preview = messages[0]['content'][:100] if messages else "(无有效消息)"
            logger.bind(tag=TAG).error(
                f"[PowerMem保存] 保存失败, user_id={user_id}, "
                f"有效消息数={len(messages)}, "
                f"首条消息前100字={msg_preview}, "
                f"error={str(e)}"
            )
            logger.bind(tag=TAG).debug(f"Detailed error: {traceback.format_exc()}")
            return None

    def _evict_if_needed(self, cache: collections.OrderedDict):
        """LRU 淘汰：缓存达到容量上限时移除最早插入的条目。"""
        if self._max_cache_size <= 0:
            return
        while len(cache) > self._max_cache_size:
            cache.popitem(last=False)

    def _invalidate_search_cache(self, user_id: str):
        """清除指定用户的搜索结果缓存。在 save_memory 后调用，因为新消息会改变搜索结果。"""
        if user_id in self._search_cache:
            del self._search_cache[user_id]
            logger.bind(tag=TAG).debug(f"[记忆缓存] 清除搜索缓存(保存后刷新), user_id={user_id}")

    def _get_search_cache(self, user_id: str):
        """
        获取搜索结果缓存。返回 (cached_result, is_hit)。
        缓存过期或不存在时返回 (None, False)。

        滑动 TTL：每次命中时重新计算过期时间，避免持续活跃的会话因固定 TTL
        过期而频繁回查数据库。
        """
        if self._search_cache_ttl <= 0:
            return None, False

        entry = self._search_cache.get(user_id)
        if entry is None:
            return None, False

        cached_result, expire_time = entry
        if time.time() > expire_time:
            # 缓存已过期，清除
            del self._search_cache[user_id]
            logger.bind(tag=TAG).debug(f"[记忆缓存] 搜索缓存已过期, user_id={user_id}")
            return None, False

        # 滑动 TTL：命中时刷新过期时间
        self._search_cache[user_id] = (cached_result, time.time() + self._search_cache_ttl)
        # LRU：命中时移到末尾
        self._search_cache.move_to_end(user_id)
        return cached_result, True

    def _set_search_cache(self, user_id: str, result: str):
        """
        设置搜索结果缓存。TTL 由 memory_cache_ttl 配置项控制（默认60秒，设为0禁用）。
        """
        if self._search_cache_ttl <= 0:
            return

        self._search_cache[user_id] = (result, time.time() + self._search_cache_ttl)
        self._search_cache.move_to_end(user_id)
        self._evict_if_needed(self._search_cache)
        logger.bind(tag=TAG).debug(f"[记忆缓存] 写入搜索缓存, user_id={user_id}, TTL={self._search_cache_ttl}s")

    async def query_memory(self, query: str, user_id: str = None) -> str:
        """
        Query memories from PowerMem based on similarity search.

        同一轮对话中，对同一 user_id 的搜索结果会缓存在内存中（TTL 由 memory_cache_ttl 控制，
        默认60秒），避免重复调用 PowerMem search() 浪费资源。调用 save_memory() 后缓存会自动失效。

        性能优化：
        - 画像查询和记忆搜索通过 asyncio.gather 并行执行，互不阻塞
        - 画像查询有 5 秒超时保护，超时返回空画像不影响对话
        - 搜索 limit 默认 15 条（通过 search_limit 配置），减少数据库查询压力

        Args:
            query: The search query string (may be JSON format with metadata)
            user_id: PowerMem user_id for isolation (defaults to self.role_id)

        Returns:
            Formatted string of relevant memories or empty string if none found
        """
        if not self.use_powermem or self.memory_client is None:
            logger.bind(tag=TAG).warning("[PowerMem查询] PowerMem不可用，跳过query_memory")
            return ""

        user_id = user_id or self.role_id
        if not user_id:
            logger.bind(tag=TAG).warning(f"[PowerMem查询] user_id为空(self.role_id={self.role_id})，返回空记忆")
            return ""

        # 声纹记忆按 {device_id}:{姓名} 隔离，兼容旧 :person: 格式
        user_id = self._resolve_user_id(user_id, query)

        try:
            # Extract content from JSON format if present (for ASR with emotion/language tags)
            # 复用 _extract_text_from_content 保持与 save_memory 处理逻辑一致
            search_query = self._extract_text_from_content(query)

            # 检查搜索结果缓存，同一轮对话中避免重复调用 PowerMem search()
            cached_result, is_hit = self._get_search_cache(user_id)
            if is_hit:
                logger.bind(tag=TAG).info(
                    f"[PowerMem查询] 搜索缓存命中, user_id={user_id}, "
                    f"缓存结果长度={len(cached_result)}, 跳过SDK调用"
                )
                # 画像部分仍需检查（画像缓存独立于搜索缓存）
                result_parts = []
                if self.enable_user_profile:
                    profile = await self.get_user_profile(user_id=user_id)
                    if profile:
                        result_parts.append(f"【用户画像】\n{profile}")
                if cached_result:
                    result_parts.append(cached_result)
                return "\n\n".join(result_parts) if result_parts else ""

            logger.bind(tag=TAG).info(
                f"[PowerMem查询] 开始查询, user_id={user_id}, 原始query={query[:80]}, 提取后search_query={search_query[:80]}"
            )

            result_parts = []

            # 并行执行画像查询和记忆搜索，互不阻塞
            # 画像查询有 5 秒超时保护，搜索 limit 默认 15 条
            coros = []

            if self.enable_user_profile:
                coros.append(
                    asyncio.create_task(self.get_user_profile(user_id=user_id))
                )

            # Search memories using PowerMem SDK (hybrid retrieval: vector + full-text + knowledge graph)
            # UserMemory.search 为同步接口，需 asyncio.to_thread 包裹；AsyncMemory.search 为异步接口，直接 await
            if self.enable_user_profile:
                search_coro = asyncio.to_thread(
                    self.memory_client.search,
                    query=search_query,
                    user_id=user_id,
                    limit=self._search_limit
                )
            else:
                # AsyncMemory: 混合检索（向量+全文+知识图谱），异步接口直接 await
                search_coro = self.memory_client.search(
                    query=search_query,
                    user_id=user_id,
                    limit=self._search_limit
                )
            coros.append(asyncio.create_task(search_coro))

            # 通过 asyncio.gather 真正并行执行，总耗时取两者最大值而非之和
            gathered = await asyncio.gather(*coros, return_exceptions=True)

            # 解析结果
            gather_idx = 0
            if self.enable_user_profile:
                profile_result = gathered[gather_idx]
                gather_idx += 1
                if isinstance(profile_result, Exception):
                    logger.bind(tag=TAG).error(
                        f"[PowerMem查询] 画像查询异常, user_id={user_id}, error={profile_result}"
                    )
                    profile = ""
                else:
                    profile = profile_result
                logger.bind(tag=TAG).info(
                    f"[PowerMem查询] 画像查询结果, user_id={user_id}, "
                    f"有画像={bool(profile)}"
                )
                if profile:
                    result_parts.append(f"【用户画像】\n{profile}")

            search_result = gathered[gather_idx]
            if isinstance(search_result, Exception):
                logger.bind(tag=TAG).error(
                    f"[PowerMem查询] 记忆搜索异常, user_id={user_id}, error={search_result}"
                )
                results = None
            else:
                results = search_result

            logger.bind(tag=TAG).info(
                f'[PowerMem查询] SDK返回结果, user_id={user_id}, results_keys={list(results.keys()) if results else "None"}, 结果数量={len(results.get("results", [])) if results and "results" in results else "N/A"}'
            )

            # 初始化 memories_part，确保在搜索异常或结果为空时也有定义
            memories_part = ""

            if results and "results" in results:
                # Format each memory entry with its update time
                # 按时间倒序排列，最新记忆优先展示；PowerMem 底层还通过艾宾浩斯遗忘曲线进行相关性衰减
                memories = []
                for entry in results.get("results", []):
                    # Get timestamp from updated_at or created_at
                    timestamp = ""
                    if "updated_at" in entry and entry["updated_at"]:
                        timestamp = str(entry["updated_at"])
                    elif "created_at" in entry and entry["created_at"]:
                        timestamp = str(entry["created_at"])

                    if timestamp:
                        try:
                            # Parse and reformat the timestamp (remove milliseconds if present)
                            if "." in timestamp:
                                dt = timestamp.split(".")[0]
                            else:
                                dt = timestamp
                            formatted_time = dt.replace("T", " ")
                        except Exception:
                            formatted_time = timestamp
                    else:
                        formatted_time = ""

                    memory = entry.get("memory", "") or entry.get("content", "")
                    if memory:
                        if formatted_time:
                            # Store tuple of (timestamp, formatted_string) for sorting
                            memories.append((timestamp, f"[{formatted_time}] {memory}"))
                        else:
                            memories.append(("", memory))

                # Sort by timestamp in descending order (newest first)
                memories.sort(key=lambda x: x[0], reverse=True)

                # Extract only the formatted strings
                if memories:
                    memories_part = "\n".join(f"- {memory[1]}" for memory in memories)
                    result_parts.append(f"【相关记忆】\n{memories_part}")

            final_result = "\n\n".join(result_parts)

            # 将搜索结果（记忆部分）写入会话级缓存，同一轮对话中重复查询直接返回
            # 缓存的是格式化后的记忆字符串，不包含用户画像（画像有独立缓存）
            if memories_part:
                self._set_search_cache(user_id, memories_part)

            logger.bind(tag=TAG).info(
                f"[PowerMem查询] 查询完成, user_id={user_id}, 结果长度={len(final_result)}, 内容前300字={final_result[:300] if final_result else '(空)'}"
            )
            return final_result

        except Exception as e:
            logger.bind(tag=TAG).error(f"[PowerMem查询] 查询失败, user_id={user_id}, query={query[:80]}, error={str(e)}")
            logger.bind(tag=TAG).debug(f"Detailed error: {traceback.format_exc()}")
            return ""

    async def _background_refresh_profile(self, cache_key: str):
        """后台异步刷新用户画像缓存。

        当 get_user_profile 超时后，启动此任务在后台继续查询数据库。
        查询成功后回填 TTL 缓存和旧版缓存，下次查询可直接命中缓存。

        Args:
            cache_key: 用户画像缓存 key（user_id）
        """
        try:
            logger.bind(tag=TAG).info(
                f"[用户画像] 后台刷新开始, user_id={cache_key}"
            )
            # 无超时限制的后台查询，确保能完成
            profile_result = await asyncio.to_thread(
                self.memory_client.profile,
                user_id=cache_key
            )

            if profile_result:
                profile_text = self._parse_profile_result(profile_result)

                if profile_text:
                    # 回填 TTL 缓存
                    self._profile_cache[cache_key] = (profile_text, time.time() + self._profile_cache_ttl)
                    self._evict_if_needed(self._profile_cache)
                    logger.bind(tag=TAG).info(
                        f"[用户画像] 后台刷新成功, user_id={cache_key}, "
                        f"画像前100字={profile_text[:100]}, "
                        f"缓存TTL={self._profile_cache_ttl}s"
                    )
                else:
                    logger.bind(tag=TAG).debug(f"[用户画像] 后台刷新：数据库中无画像内容, user_id={cache_key}")
            else:
                logger.bind(tag=TAG).debug(f"[用户画像] 后台刷新：数据库中无画像记录, user_id={cache_key}")
        except Exception as e:
            logger.bind(tag=TAG).error(
                f"[用户画像] 后台刷新失败, user_id={cache_key}, error={str(e)}"
            )
        finally:
            # 清理任务跟踪，允许下次超时后重新启动
            if cache_key in self._profile_refresh_tasks:
                del self._profile_refresh_tasks[cache_key]

    async def get_user_profile(self, user_id: str = None) -> str:
        """
        Get user profile from PowerMem (only available in UserMemory mode).

        优先从 TTL 缓存获取，缓存 miss 时主动调用 PowerMem profile() API
        从数据库查询，查询成功后回填缓存。

        超时保护：数据库查询超过 5 秒时超时返回空字符串，不阻塞对话流程。

        Args:
            user_id: PowerMem user_id (defaults to self.role_id)

        Returns:
            Formatted user profile string or empty string if not available
        """
        if not self.use_powermem or self.memory_client is None:
            return ""

        if not self.enable_user_profile:
            logger.bind(tag=TAG).debug("User profile mode is not enabled")
            return ""

        cache_key = user_id or self.role_id
        if not cache_key:
            logger.bind(tag=TAG).warning("[用户画像] user_id和role_id均为空，跳过画像查询")
            return ""

        # 优先从 TTL 缓存获取（滑动 TTL：命中时刷新过期时间）
        if cache_key in self._profile_cache:
            cached_text, expire_time = self._profile_cache[cache_key]
            if time.time() <= expire_time:
                logger.bind(tag=TAG).debug(f"[用户画像] 命中TTL缓存, user_id={cache_key}")
                # 滑动 TTL：命中时刷新过期时间，避免持续活跃的会话频繁回查数据库
                self._profile_cache[cache_key] = (cached_text, time.time() + self._profile_cache_ttl)
                return cached_text
            else:
                # 缓存过期，清除
                del self._profile_cache[cache_key]

        # 缓存 miss：主动调用 PowerMem profile() API 从数据库查询
        # UserMemory.profile 为同步接口，需 asyncio.to_thread 包裹
        # 加 5 秒超时保护，避免数据库慢查询阻塞对话
        try:
            logger.bind(tag=TAG).info(f"[用户画像] 缓存未命中, 主动查询数据库, user_id={cache_key}")
            profile_result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.memory_client.profile,
                    user_id=cache_key
                ),
                timeout=5.0
            )

            if profile_result:
                profile_text = self._parse_profile_result(profile_result)

                if profile_text:
                    # 回填 TTL 缓存
                    self._profile_cache[cache_key] = (profile_text, time.time() + self._profile_cache_ttl)
                    self._evict_if_needed(self._profile_cache)
                    logger.bind(tag=TAG).info(
                        f"[用户画像] 数据库查询成功, user_id={cache_key}, "
                        f"画像前100字={profile_text[:100]}, "
                        f"缓存TTL={self._profile_cache_ttl}s"
                    )
                    return profile_text
                else:
                    logger.bind(tag=TAG).debug(f"[用户画像] 数据库中无画像内容, user_id={cache_key}")
            else:
                logger.bind(tag=TAG).debug(f"[用户画像] 数据库中无画像记录, user_id={cache_key}")
        except asyncio.TimeoutError:
            logger.bind(tag=TAG).warning(
                f"[用户画像] 数据库查询超时(5s), user_id={cache_key}, 返回空画像"
            )
            # 超时后启动后台异步任务继续查询，查询成功后回填缓存
            # 避免重复启动：如果已有同一 user_id 的后台刷新任务在运行，则跳过
            if cache_key not in self._profile_refresh_tasks or self._profile_refresh_tasks[cache_key].done():
                self._profile_refresh_tasks[cache_key] = asyncio.create_task(
                    self._background_refresh_profile(cache_key)
                )
                logger.bind(tag=TAG).info(
                    f"[用户画像] 已启动后台刷新任务, user_id={cache_key}"
                )
        except Exception as e:
            logger.bind(tag=TAG).error(f"[用户画像] 数据库查询失败, user_id={cache_key}, error={str(e)}")

        return ""

