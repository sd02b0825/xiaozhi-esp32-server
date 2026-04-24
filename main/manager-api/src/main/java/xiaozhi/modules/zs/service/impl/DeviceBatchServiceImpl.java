package xiaozhi.modules.zs.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.user.UserDetail;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.zs.dto.DeviceBatchAddDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO.FailItemDTO;
import xiaozhi.modules.zs.service.DeviceBatchService;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeviceBatchServiceImpl implements DeviceBatchService {

    private final DeviceDao deviceDao;

    @Override
    public DeviceBatchAddRespDTO batchAddDevice(DeviceBatchAddDTO dto) {
        DeviceBatchAddRespDTO resp = new DeviceBatchAddRespDTO();
        List<FailItemDTO> failList = new ArrayList<>();
        int successCount = 0;

        for (DeviceBatchAddDTO.DeviceItemDTO item : dto.getDevices()) {
            try {
                // 1. 检查设备是否已存在
                DeviceEntity existDevice = getDeviceByMacAddress(item.getMacAddress());
                if (existDevice != null) {
                    failList.add(new FailItemDTO(item.getMacAddress(), "设备已存在"));
                    continue;
                }
                UserDetail user = SecurityUser.getUser();
                // 2. 创建设备记录
                Date now = new Date();
                DeviceEntity device = new DeviceEntity();
                device.setId(item.getMacAddress());
                device.setMacAddress(item.getMacAddress());
                device.setBoard(item.getBoard());
                device.setVerifyCode(item.getVerifyCode());
                device.setUserId(user.getId());
                device.setCreator(user.getId());
                device.setCreateDate(now);
                device.setAppVersion("2.0.0");
                device.setUpdater(user.getId());
                device.setUpdateDate(now);
                device.setLastConnectedAt(now);
                device.setAutoUpdate(1);
                deviceDao.insert(device);

                successCount++;
            } catch (Exception e) {
                log.error("批量录入设备失败: macAddress={}", item.getMacAddress(), e);
                failList.add(new FailItemDTO(item.getMacAddress(), "系统错误: " + e.getMessage()));
            }
        }

        resp.setSuccessCount(successCount);
        resp.setFailCount(failList.size());
        resp.setFailList(failList);
        return resp;
    }

    private DeviceEntity getDeviceByMacAddress(String macAddress) {
        QueryWrapper<DeviceEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("mac_address", macAddress);
        return deviceDao.selectOne(wrapper);
    }
}
