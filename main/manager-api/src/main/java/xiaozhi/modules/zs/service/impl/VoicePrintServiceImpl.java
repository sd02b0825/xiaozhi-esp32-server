package xiaozhi.modules.zs.service.impl;

import java.util.Base64;
import java.util.List;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.agent.entity.AgentChatHistoryEntity;
import xiaozhi.modules.agent.entity.AgentVoicePrintEntity;
import xiaozhi.modules.agent.service.AgentChatAudioService;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentVoicePrintService;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dto.VoicePrintRespDTO;
import xiaozhi.modules.zs.dto.VoicePrintSaveDTO;
import xiaozhi.modules.zs.dto.VoicePrintUpdateDTO;
import xiaozhi.modules.zs.service.VoicePrintService;

/**
 * 声纹录音服务实现
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VoicePrintServiceImpl implements VoicePrintService {

    private final DeviceDao deviceDao;
    private final AgentVoicePrintService agentVoicePrintService;
    private final AgentChatHistoryService agentChatHistoryService;
    private final AgentChatAudioService agentChatAudioService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public VoicePrintRespDTO save(Long userId, VoicePrintSaveDTO dto) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCode(dto.getVerifyCode(), userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }
        if (StringUtils.isBlank(device.getAgentId())) {
            throw new RenException("设备未绑定智能体");
        }

        // 2. 处理音频：优先使用 audioBase64，否则使用 audioId
        String audioId = dto.getAudioId();
        if (StringUtils.isBlank(audioId) && StringUtils.isNotBlank(dto.getAudioBase64())) {
            // Base64解码并存储音频
            try {
                byte[] audioData = Base64.getDecoder().decode(dto.getAudioBase64());
                audioId = agentChatAudioService.saveAudio(audioData);
                log.info("声纹音频Base64解码并存储成功，audioId={}", audioId);
            } catch (Exception e) {
                log.error("声纹音频Base64解码失败", e);
                throw new RenException("音频数据解析失败");
            }
        }

        if (StringUtils.isBlank(audioId)) {
            throw new RenException("音频ID或音频数据不能都为空");
        }

        // 3. 将音频插入聊天记录（如果尚未关联），确保归属检查能通过
        saveAudioToChatHistory(audioId, device.getAgentId(),
                dto.getMacAddress() != null ? dto.getMacAddress() : device.getMacAddress());

        // 4. 构建保存DTO并调用服务
        xiaozhi.modules.agent.dto.AgentVoicePrintSaveDTO saveDto =
                new xiaozhi.modules.agent.dto.AgentVoicePrintSaveDTO();
        saveDto.setAgentId(device.getAgentId());
        saveDto.setAudioId(audioId);
        saveDto.setSourceName(dto.getSourceName());
        saveDto.setIntroduce(dto.getIntroduce());

        boolean success = agentVoicePrintService.insert(saveDto);
        if (!success) {
            throw new RenException("声纹保存失败");
        }

        // 5. 查询并返回
        return getByAgentId(device.getAgentId(), userId).stream()
                .filter(vp -> dto.getSourceName().equals(vp.getSourceName()))
                .findFirst()
                .orElseThrow(() -> new RenException("声纹保存后查询失败"));
    }

    @Override
    public List<VoicePrintRespDTO> list(Long userId, String verifyCode) {
        DeviceEntity device = getDeviceByVerifyCode(verifyCode, userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }
        if (StringUtils.isBlank(device.getAgentId())) {
            throw new RenException("设备未绑定智能体");
        }
        return getByAgentId(device.getAgentId(), userId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public VoicePrintRespDTO update(Long userId, VoicePrintUpdateDTO dto) {
        // 1. 根据验证码查询设备
        DeviceEntity device = getDeviceByVerifyCodeWithAgent(dto.getVerifyCode(), userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }

        // 2. 构建更新DTO并调用服务
        xiaozhi.modules.agent.dto.AgentVoicePrintUpdateDTO updateDto =
                new xiaozhi.modules.agent.dto.AgentVoicePrintUpdateDTO();
        updateDto.setId(dto.getId());
        updateDto.setAudioId(dto.getAudioId());
        updateDto.setSourceName(dto.getSourceName());
        updateDto.setIntroduce(dto.getIntroduce());

        boolean success = agentVoicePrintService.update(userId, updateDto);
        if (!success) {
            throw new RenException("声纹更新失败");
        }

        // 3. 查询并返回
        return getByAgentId(device.getAgentId(), userId).stream()
                .filter(vp -> dto.getId().equals(vp.getId()))
                .findFirst()
                .orElseThrow(() -> new RenException("声纹更新后查询失败"));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long userId, String verifyCode, String voiceId) {
        DeviceEntity device = getDeviceByVerifyCode(verifyCode, userId);
        if (device == null) {
            throw new RenException("设备不存在");
        }
        boolean success = agentVoicePrintService.delete(userId, voiceId);
        if (!success) {
            throw new RenException("声纹删除失败");
        }
    }

    private DeviceEntity getDeviceByVerifyCode(String verifyCode, Long userId) {
        return deviceDao.selectOne(new LambdaQueryWrapper<DeviceEntity>()
                .eq(DeviceEntity::getVerifyCode, verifyCode)
                .eq(DeviceEntity::getUserId, userId));
    }

    private DeviceEntity getDeviceByVerifyCodeWithAgent(String verifyCode, Long userId) {
        DeviceEntity device = getDeviceByVerifyCode(verifyCode, userId);
        if (device != null && StringUtils.isBlank(device.getAgentId())) {
            throw new RenException("设备未绑定智能体");
        }
        return device;
    }

    private List<VoicePrintRespDTO> getByAgentId(String agentId, Long userId) {
        List<xiaozhi.modules.agent.vo.AgentVoicePrintVO> voList =
                agentVoicePrintService.list(userId, agentId);
        return voList.stream().map(vo -> {
            VoicePrintRespDTO dto = new VoicePrintRespDTO();
            dto.setId(vo.getId());
            dto.setAudioId(vo.getAudioId());
            dto.setSourceName(vo.getSourceName());
            dto.setIntroduce(vo.getIntroduce());
            dto.setCreateDate(vo.getCreateDate() != null ?
                    new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(vo.getCreateDate()) : null);
            return dto;
        }).collect(Collectors.toList());
    }

    /**
     * 将音频插入聊天记录（如果尚未关联到当前智能体）
     *
     * @param audioId     音频ID
     * @param agentId     智能体ID
     * @param macAddress  MAC地址
     */
    private void saveAudioToChatHistory(String audioId, String agentId, String macAddress) {
        // 检查音频是否已关联到当前智能体
        if (!agentChatHistoryService.isAudioOwnedByAgent(audioId, agentId)) {
            // 创建一条聊天记录，将音频关联到智能体
            AgentChatHistoryEntity entity = AgentChatHistoryEntity.builder()
                    .audioId(audioId)
                    .agentId(agentId)
                    .macAddress(macAddress != null ? macAddress : "voiceprint-registration")
                    .chatType((byte) 1) // 用户消息
                    .content("声纹注册音频")
                    .build();
            agentChatHistoryService.save(entity);
        }
    }
}
