package xiaozhi.modules.zs.service;

import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;

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
}
