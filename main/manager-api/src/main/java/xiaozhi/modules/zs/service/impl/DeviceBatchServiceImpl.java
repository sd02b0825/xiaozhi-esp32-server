package xiaozhi.modules.zs.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.user.UserDetail;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.zs.dto.DeviceBatchAddDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO.FailItemDTO;
import xiaozhi.modules.zs.dto.DeviceVerifyCodeUpdateDTO;
import xiaozhi.modules.zs.service.DeviceBatchService;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeviceBatchServiceImpl implements DeviceBatchService {

    private static final String DEFAULT_BOARD = "ESP32-S3-BOX";

    private final DeviceDao deviceDao;

    @Override
    public DeviceBatchAddRespDTO batchAddDevice(DeviceBatchAddDTO dto) {
        DeviceBatchAddRespDTO resp = new DeviceBatchAddRespDTO();
        List<FailItemDTO> failList = new ArrayList<>();
        int successCount = 0;
        UserDetail user = SecurityUser.getUser();
        Set<String> requestMacSet = new HashSet<>();
        Set<String> requestVerifyCodeSet = new HashSet<>();

        for (DeviceBatchAddDTO.DeviceItemDTO item : dto.getDevices()) {
            try {
                String macAddress = item.getMacAddress();
                String verifyCode = item.getVerifyCode();

                // 1. 校验本次请求内是否重复
                if (!requestMacSet.add(macAddress)) {
                    failList.add(new FailItemDTO(macAddress, "同一批次中MAC地址重复"));
                    continue;
                }
                if (!requestVerifyCodeSet.add(verifyCode)) {
                    failList.add(new FailItemDTO(macAddress, "同一批次中验证码重复"));
                    continue;
                }

                // 2. 检查MAC地址是否已存在
                DeviceEntity existDevice = getDeviceByMacAddress(macAddress);
                if (existDevice != null) {
                    failList.add(new FailItemDTO(macAddress, "设备已存在"));
                    continue;
                }

                // 3. 检查当前用户下验证码是否已存在（绑定流程依赖验证码唯一）
                DeviceEntity verifyCodeDevice = getDeviceByVerifyCode(verifyCode, user.getId());
                if (verifyCodeDevice != null) {
                    failList.add(new FailItemDTO(macAddress, "验证码已存在"));
                    continue;
                }

                // 4. 创建设备记录
                Date now = new Date();
                DeviceEntity device = new DeviceEntity();
                device.setId(macAddress);
                device.setMacAddress(macAddress);
                device.setBoard(DEFAULT_BOARD);
                device.setVerifyCode(verifyCode);
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

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateVerifyCode(DeviceVerifyCodeUpdateDTO dto) {
        UserDetail user = SecurityUser.getUser();
        String mac = StringUtils.trimToEmpty(dto.getMacAddress());
        String newCode = StringUtils.trimToEmpty(dto.getNewVerifyCode());
        if (StringUtils.isAnyBlank(mac, newCode)) {
            throw new RenException("MAC地址或新验证码不能为空");
        }

        DeviceEntity device = getDeviceByMacAndUser(mac, user.getId());
        if (device == null) {
            throw new RenException("设备不存在");
        }

        DeviceEntity other = getDeviceByVerifyCode(newCode, user.getId());
        if (other != null && !other.getId().equals(device.getId())) {
            throw new RenException("验证码已存在");
        }

        Date now = new Date();
        device.setVerifyCode(newCode);
        device.setUpdater(user.getId());
        device.setUpdateDate(now);
        deviceDao.updateById(device);
    }

    private DeviceEntity getDeviceByMacAndUser(String macAddress, Long userId) {
        return deviceDao.selectOne(new LambdaQueryWrapper<DeviceEntity>()
                .eq(DeviceEntity::getMacAddress, macAddress)
                .eq(DeviceEntity::getUserId, userId));
    }

    private DeviceEntity getDeviceByMacAddress(String macAddress) {
        QueryWrapper<DeviceEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("mac_address", macAddress);
        return deviceDao.selectOne(wrapper);
    }

    private DeviceEntity getDeviceByVerifyCode(String verifyCode, Long userId) {
        QueryWrapper<DeviceEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("verify_code", verifyCode);
        wrapper.eq("user_id", userId);
        return deviceDao.selectOne(wrapper);
    }
}
