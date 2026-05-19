package xiaozhi.modules.zs.service.impl;

import java.util.Base64;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.agent.entity.AgentChatHistoryEntity;
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

        // 2. 处理音频列表并存储
        List<String> audioBase64List = dto.getAudioBase64List();
        if (audioBase64List == null || audioBase64List.isEmpty()) {
            throw new RenException("音频数据列表不能为空");
        }
        List<String> audioIdList = new ArrayList<>();
        for (String audioBase64 : audioBase64List) {
            if (StringUtils.isBlank(audioBase64)) {
                continue;
            }
            try {
                byte[] audioData = Base64.getDecoder().decode(audioBase64);
                String audioId = agentChatAudioService.saveAudio(audioData);
                audioIdList.add(audioId);
                log.info("声纹音频Base64解码并存储成功，audioId={}", audioId);
            } catch (Exception e) {
                log.error("声纹音频Base64解码失败", e);
                throw new RenException("音频数据解析失败");
            }
        }
        if (audioIdList.isEmpty()) {
            throw new RenException("音频数据列表不能为空");
        }

        // 3. 将所有音频插入聊天记录（如果尚未关联），确保归属检查能通过
        String macAddress = dto.getMacAddress() != null ? dto.getMacAddress() : device.getMacAddress();
        String sessionId = UUID.randomUUID().toString();
        for (int i = 0; i < audioIdList.size(); i++) {
            String audioId = audioIdList.get(i);
            saveAudioToChatHistory(audioId, device.getAgentId(), macAddress, dto.getSourceName(), i + 1, sessionId);
        }

        // 4. 每段音频都单独保存并注册声纹
        for (String audioId : audioIdList) {
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
        }

        // 5. 查询并返回本次保存结果，聚合本次上传产生的全部声纹ID
        List<VoicePrintRespDTO> savedVoicePrintList = getByAgentId(device.getAgentId(), userId).stream()
                .filter(vp -> containsAnyAudioId(vp, audioIdList))
                .collect(Collectors.toList());
        if (savedVoicePrintList.size() < audioIdList.size()) {
            throw new RenException("声纹保存后查询失败");
        }
        VoicePrintRespDTO respDTO = savedVoicePrintList.stream()
                .filter(vp -> containsAudioId(vp, audioIdList.get(0)))
                .findFirst()
                .orElse(savedVoicePrintList.get(0));
        respDTO.setIdList(savedVoicePrintList.stream()
                .flatMap(vp -> vp.getIdList().stream())
                .collect(Collectors.toList()));
        return respDTO;
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
                .filter(vp -> containsId(vp, dto.getId()))
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
            dto.setIdList(StringUtils.isNotBlank(vo.getId())
                    ? Collections.singletonList(vo.getId())
                    : Collections.emptyList());
            dto.setAudioId(vo.getAudioId());
            dto.setSourceName(vo.getSourceName());
            dto.setIntroduce(vo.getIntroduce());
            dto.setCreateDate(vo.getCreateDate() != null ?
                    new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(vo.getCreateDate()) : null);
            return dto;
        }).collect(Collectors.toList());
    }

    private boolean containsAnyAudioId(VoicePrintRespDTO dto, List<String> audioIdList) {
        return StringUtils.isNotBlank(dto.getAudioId()) && audioIdList.contains(dto.getAudioId());
    }

    private boolean containsAudioId(VoicePrintRespDTO dto, String audioId) {
        return StringUtils.equals(dto.getAudioId(), audioId);
    }

    private boolean containsId(VoicePrintRespDTO dto, String id) {
        return dto.getIdList() != null && dto.getIdList().contains(id);
    }

    /**
     * 将音频插入聊天记录（如果尚未关联到当前智能体）
     *
     * @param audioId     音频ID
     * @param agentId     智能体ID
     * @param macAddress  MAC地址
     */
    private void saveAudioToChatHistory(String audioId, String agentId, String macAddress, String sourceName,
            int index, String sessionId) {
        String displayName = StringUtils.isNotBlank(sourceName) ? sourceName : "未命名";
        // isAudioOwnedByAgent：恰好一条 (audioId + agentId) 时视为已关联并跳过插入。
        // 若该条为历史数据且 session_id 为空，这里必须补齐，否则会话列表里会一直出现 sessionId 为 null 的分组。
        if (!agentChatHistoryService.isAudioOwnedByAgent(audioId, agentId)) {
            AgentChatHistoryEntity entity = new AgentChatHistoryEntity();
            entity.setAudioId(audioId);
            entity.setAgentId(agentId);
            entity.setSessionId(sessionId);
            entity.setMacAddress(macAddress != null ? macAddress : "voiceprint-registration");
            entity.setChatType((byte) 1); // 用户消息
            entity.setContent("声纹注册音频-" + displayName + "-" + index);
            agentChatHistoryService.save(entity);
        } else {
            agentChatHistoryService.update(new LambdaUpdateWrapper<AgentChatHistoryEntity>()
                    .set(AgentChatHistoryEntity::getSessionId, sessionId)
                    .eq(AgentChatHistoryEntity::getAudioId, audioId)
                    .eq(AgentChatHistoryEntity::getAgentId, agentId)
                    .and(w -> w.isNull(AgentChatHistoryEntity::getSessionId)
                            .or()
                            .eq(AgentChatHistoryEntity::getSessionId, "")));
        }
    }
}
