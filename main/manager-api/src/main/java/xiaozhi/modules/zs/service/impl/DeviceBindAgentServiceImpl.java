package xiaozhi.modules.zs.service.impl;

import java.util.Date;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.agent.dto.AgentCreateDTO;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;
import xiaozhi.modules.zs.service.DeviceBindAgentService;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeviceBindAgentServiceImpl implements DeviceBindAgentService {

    private final DeviceDao deviceDao;
    private final AgentService agentService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public DeviceBindAgentRespDTO bindAgent(Long userId, DeviceBindAgentDTO dto) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(dto.getVerifyCode(), userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 检查设备是否已绑定智能体
        if (StringUtils.isNotBlank(device.getAgentId())) {
            throw new RenException("设备已绑定其他智能体");
        }

        // 3. 使用AgentService创建智能体
        AgentCreateDTO agentCreateDTO = new AgentCreateDTO();
        agentCreateDTO.setAgentName(dto.getAgentName());
        String agentId = agentService.createAgent(agentCreateDTO);

        // 4. 更新设备的智能体ID
        device.setAgentId(agentId);
        device.setUpdater(userId);
        device.setUpdateDate(new Date());
        deviceDao.updateById(device);

        // 5. 构建响应
        DeviceBindAgentRespDTO resp = new DeviceBindAgentRespDTO();
        resp.setAgentId(agentId);
        resp.setAgentName(dto.getAgentName());
        resp.setDeviceId(device.getId());
        resp.setMacAddress(device.getMacAddress());
        return resp;
    }

    private DeviceEntity getDeviceByVerifyCode(String verifyCode, Long userId) {
        QueryWrapper<DeviceEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("verify_code", verifyCode);
        wrapper.eq("user_id", userId);
        return deviceDao.selectOne(wrapper);
    }
}
