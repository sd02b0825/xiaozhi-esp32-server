from typing import Dict, Any, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from core.connection import ConnectionHandler
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType

TAG = __name__


class StateTextMessageHandler(TextMessageHandler):
    """State消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.STATE

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        """处理state类型消息"""
        
        # 获取state状态
        state = msg_json.get("state")
        conn.client_state = state
        conn.logger.bind(tag=TAG).info(f"state状态: {state}")
        
        # if state == "speaking":
        #     # 处理开始状态
        #     conn.client_is_speaking = True
        #     # 取消可能存在的延迟设置任务
        #     if hasattr(conn, "set_client_not_speaking_task") and conn.set_client_not_speaking_task and not conn.set_client_not_speaking_task.done():
        #         conn.set_client_not_speaking_task.cancel()
        # else:
        #     # 处理停止状态，等待2秒后再设置为false
        #     async def set_client_not_speaking():
        #         await asyncio.sleep(2)
        #         conn.clear_queues()
        #         conn.client_is_speaking = False
        #         conn.logger.bind(tag=TAG).info("2秒延迟后设置client_is_speaking为False")
            
        #     conn.set_client_not_speaking_task = asyncio.create_task(set_client_not_speaking())
