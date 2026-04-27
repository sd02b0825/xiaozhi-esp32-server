package xiaozhi.modules.zs.service;

import xiaozhi.common.page.PageData;
import xiaozhi.modules.agent.dto.AgentChatHistoryDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;
import xiaozhi.modules.zs.dto.DeviceUpdateAgentDTO;

/**
 * 设备绑定智能体服务接口
 */
public interface DeviceBindAgentService {

    /**
     * 设备绑定智能体
     *
     * @param userId 用户ID
     * @param dto    绑定请求参数
     * @return 绑定结果
     */
    DeviceBindAgentRespDTO bindAgent(Long userId, DeviceBindAgentDTO dto);

    /**
     * 修改设备绑定的智能体信息
     *
     * @param userId  用户ID
     * @param agentId 智能体ID
     * @param dto     修改请求参数
     * @return 修改结果
     */
    DeviceBindAgentRespDTO updateAgent(Long userId, String agentId, DeviceUpdateAgentDTO dto);

    /**
     * 删除设备绑定的智能体
     *
     * @param userId  用户ID
     * @param agentId 智能体ID
     */
    void deleteAgent(Long userId, String agentId);

    /**
     * 查询智能体全部聊天记录（分页）
     *
     * @param userId  用户ID
     * @param agentId 智能体ID
     * @param page    页码（从1开始）
     * @param limit   每页数量
     * @return 聊天记录分页数据
     */
    PageData<AgentChatHistoryDTO> getAgentChatHistory(Long userId, String agentId, Integer page, Integer limit);
}
