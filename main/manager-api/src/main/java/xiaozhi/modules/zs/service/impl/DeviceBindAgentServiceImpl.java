package xiaozhi.modules.zs.service.impl;

import java.util.Date;
import java.util.List;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.utils.ConvertUtils;
import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.agent.dto.AgentChatHistoryDTO;
import xiaozhi.modules.agent.dto.AgentCreateDTO;
import xiaozhi.modules.agent.entity.AgentChatHistoryEntity;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;
import xiaozhi.modules.zs.dto.DeviceUpdateAgentDTO;
import xiaozhi.modules.zs.service.DeviceBindAgentService;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeviceBindAgentServiceImpl implements DeviceBindAgentService {

    private static final String DEFAULT_BOARD = "ESP32-S3-BOX";
    private static final String DEFAULT_APP_VERSION = "2.0.0";
    private static final String DEFAULT_MEMORY_MODEL_ID = "Memory_mem_local_short";

    private final DeviceDao deviceDao;
    private final AgentService agentService;
    private final AgentDao agentDao;
    private final AgentChatHistoryService agentChatHistoryService;
    private final RedisUtils redisUtils;

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
        if (StringUtils.isBlank(device.getBoard())) {
            device.setBoard(DEFAULT_BOARD);
        }
        if (StringUtils.isBlank(device.getAppVersion())) {
            device.setAppVersion(DEFAULT_APP_VERSION);
        }
        if (device.getAutoUpdate() == null) {
            device.setAutoUpdate(1);
        }
        device.setUpdater(userId);
        device.setUpdateDate(new Date());
        deviceDao.updateById(device);
        redisUtils.delete(RedisKeys.getAgentDeviceCountById(agentId));

        // 5. 更新智能体的唤醒词
        AgentEntity agent = new AgentEntity();
        agent.setId(agentId);
        agent.setWakeWord(dto.getAgentName());
        agent.setMemModelId(DEFAULT_MEMORY_MODEL_ID);
        agent.setChatHistoryConf(Constant.ChatHistoryConfEnum.RECORD_TEXT_AUDIO.getCode());
        agent.setUpdater(userId);
        agent.setUpdatedAt(new Date());
        agentDao.updateById(agent);

        // 6. 构建响应
        DeviceBindAgentRespDTO resp = new DeviceBindAgentRespDTO();
        resp.setAgentId(agentId);
        resp.setAgentName(dto.getAgentName());
        resp.setDeviceId(device.getId());
        resp.setMacAddress(device.getMacAddress());
        return resp;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public DeviceBindAgentRespDTO updateAgent(Long userId, String agentId, DeviceUpdateAgentDTO dto) {
        DeviceEntity device = getDeviceByAgentId(agentId, userId);
        if (device == null) {
            throw new RenException("设备与智能体绑定关系不存在");
        }

        AgentEntity existingAgent = agentDao.selectById(agentId);
        if (existingAgent == null || !userId.equals(existingAgent.getUserId())) {
            throw new RenException("智能体不存在");
        }

        AgentEntity agent = new AgentEntity();
        agent.setId(agentId);
        agent.setAgentName(dto.getAgentName());
        agent.setWakeWord(dto.getAgentName());
        agent.setUpdater(userId);
        agent.setUpdatedAt(new Date());
        agentDao.updateById(agent);

        DeviceBindAgentRespDTO resp = new DeviceBindAgentRespDTO();
        resp.setAgentId(agentId);
        resp.setAgentName(dto.getAgentName());
        resp.setDeviceId(device.getId());
        resp.setMacAddress(device.getMacAddress());
        return resp;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteAgent(Long userId, String agentId) {
        DeviceEntity device = getDeviceByAgentId(agentId, userId);
        if (device == null) {
            throw new RenException("设备与智能体绑定关系不存在");
        }

        UpdateWrapper<DeviceEntity> updateWrapper = new UpdateWrapper<>();
        updateWrapper.eq("id", device.getId());
        updateWrapper.eq("user_id", userId);
        updateWrapper.set("agent_id", null);
        updateWrapper.set("updater", userId);
        updateWrapper.set("update_date", new Date());
        deviceDao.update(null, updateWrapper);
        redisUtils.delete(RedisKeys.getAgentDeviceCountById(agentId));
    }

    @Override
    public PageData<AgentChatHistoryDTO> getAgentChatHistory(Long userId, String agentId, Integer page, Integer limit,
            String speaker) {
        DeviceEntity device = getDeviceByAgentId(agentId, userId);
        if (device == null) {
            throw new RenException("设备与智能体绑定关系不存在");
        }

        Page<AgentChatHistoryEntity> pageParam = new Page<>(page, limit);
        QueryWrapper<AgentChatHistoryEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("agent_id", agentId);
        if (StringUtils.isNotBlank(speaker)) {
            wrapper.eq("speaker", speaker);
        }
        wrapper.orderByDesc("created_at");

        IPage<AgentChatHistoryEntity> result = agentChatHistoryService.page(pageParam, wrapper);
        List<AgentChatHistoryDTO> list = ConvertUtils.sourceToTarget(result.getRecords(), AgentChatHistoryDTO.class);
        return new PageData<>(list, result.getTotal());
    }

    private DeviceEntity getDeviceByVerifyCode(String verifyCode, Long userId) {
        QueryWrapper<DeviceEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("verify_code", verifyCode);
        wrapper.eq("user_id", userId);
        return deviceDao.selectOne(wrapper);
    }

    private DeviceEntity getDeviceByAgentId(String agentId, Long userId) {
        QueryWrapper<DeviceEntity> wrapper = new QueryWrapper<>();
        wrapper.eq("agent_id", agentId);
        wrapper.eq("user_id", userId);
        return deviceDao.selectOne(wrapper);
    }
}
