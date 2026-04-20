package xiaozhi.modules.zs.service;

import xiaozhi.modules.zs.dto.DeviceBatchAddDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO;

/**
 * 批量设备服务接口
 */
public interface DeviceBatchService {

    /**
     * 批量录入设备
     *
     * @param dto    批量录入请求参数
     * @return 批量录入结果
     */
    DeviceBatchAddRespDTO batchAddDevice(DeviceBatchAddDTO dto);
}
