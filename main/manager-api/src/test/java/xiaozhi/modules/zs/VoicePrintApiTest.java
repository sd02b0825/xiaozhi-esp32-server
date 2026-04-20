package xiaozhi.modules.zs;

import java.util.Base64;
import java.util.Date;
import java.util.List;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.agent.dto.AgentCreateDTO;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dto.VoiceCloneRespDTO;
import xiaozhi.modules.zs.dto.VoiceCloneSaveDTO;
import xiaozhi.modules.zs.dto.VoiceCloneUpdateDTO;
import xiaozhi.modules.zs.dto.VoicePrintRespDTO;
import xiaozhi.modules.zs.dto.VoicePrintSaveDTO;
import xiaozhi.modules.zs.dto.VoicePrintUpdateDTO;
import xiaozhi.modules.zs.service.VoiceCloneService;
import xiaozhi.modules.zs.service.VoicePrintService;

@Slf4j
@SpringBootTest
@ActiveProfiles("dev")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@DisplayName("声纹录音与声音克隆接口测试")
public class VoicePrintApiTest {

    /** 测试用户ID */
    protected static final Long TEST_USER_ID = 2019982586052349954L;

    private static final String TEST_MAC = "AA:BB:CC:DD:EE:12";
    private static final String TEST_VERIFY_CODE = "998879";
    private static String testAgentId;
    private static String testDeviceId;
    private static boolean setupDone = false;

    @Autowired
    private VoicePrintService voicePrintService;

    @Autowired
    private VoiceCloneService voiceCloneService;

    @Autowired
    private DeviceDao deviceDao;

    @Autowired
    private AgentDao agentDao;

    @Autowired
    private AgentService agentService;

    /**
     * 获取当前测试用户ID
     */
    protected Long getTestUserId() {
        return TEST_USER_ID;
    }

    /**
     * 前置：创建设备和智能体
     */
    private void ensureTestData() {
        if (setupDone) {
            return;
        }

        Long userId = TEST_USER_ID;
        String agentName = "TestAgent_VP_" + System.currentTimeMillis();

        // 1. 检查设备是否存在，不存在则创建
        DeviceEntity device = deviceDao.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<DeviceEntity>()
                        .eq(DeviceEntity::getVerifyCode, TEST_VERIFY_CODE));

        if (device == null) {
            device = new DeviceEntity();
            device.setId(TEST_MAC);
            device.setMacAddress(TEST_MAC);
            device.setVerifyCode(TEST_VERIFY_CODE);
            device.setBoard("esp32-s3-box");
            device.setUserId(userId);
            device.setCreator(userId);
            device.setCreateDate(new Date());
            device.setUpdater(userId);
            device.setUpdateDate(new Date());
            device.setAutoUpdate(1);
            deviceDao.insert(device);
            log.info("[Setup] 创建设备: mac={}, verifyCode={}, userId={}", TEST_MAC, TEST_VERIFY_CODE, userId);
        }

        testDeviceId = device.getId();

        // 2. 如果设备未绑定智能体，则创建一个
        if (device.getAgentId() == null) {
            AgentCreateDTO agentDTO = new AgentCreateDTO();
            agentDTO.setAgentName(agentName);
            testAgentId = agentService.createAgent(agentDTO);

            device.setAgentId(testAgentId);
            device.setUpdater(userId);
            device.setUpdateDate(new Date());
            deviceDao.updateById(device);
            log.info("[Setup] 创建并绑定智能体: agentId={}, userId={}", testAgentId, userId);
        } else {
            testAgentId = device.getAgentId();
            log.info("[Setup] 设备已绑定智能体: agentId={}", testAgentId);
        }

        setupDone = true;
    }

    // ==================== 声纹录音测试 ====================

    @Test
    @Order(1)
    @DisplayName("声纹录音 - 保存声纹（不带音频）")
    void testSaveVoicePrintWithoutAudio() {
        ensureTestData();
        log.info("=== 测试：保存声纹（不带音频）===");

        VoicePrintSaveDTO dto = new VoicePrintSaveDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setSourceName("测试称呼1");
        dto.setIntroduce("这是一个测试用称呼");
        dto.setAudioId("sssdf11111");

        VoicePrintRespDTO result = voicePrintService.save(getTestUserId(), dto);

        Assertions.assertNotNull(result, "返回结果不应为空");
        Assertions.assertNotNull(result.getId(), "声纹ID不应为空");
        Assertions.assertEquals("测试称呼1", result.getSourceName(), "称呼应一致");
        Assertions.assertEquals("这是一个测试用称呼", result.getIntroduce(), "描述应一致");

        log.info("声纹保存成功: id={}, sourceName={}", result.getId(), result.getSourceName());
    }

    @Test
    @Order(1)
    @DisplayName("声纹录音 - 保存声纹（带audioBase64）")
    void testSaveVoicePrintWithAudioBase64() {
        ensureTestData();
        log.info("=== 测试：保存声纹（带audioBase64）===");

        // 模拟一个 Opus 音频数据的 Base64 编码（这里用简单的字节数据模拟）
        // 实际使用中应该是真正的 Opus 编码音频
        String mockOpusBase64 = java.util.Base64.getEncoder()
                .encodeToString("mock_opus_audio_data_for_test".getBytes());

        VoicePrintSaveDTO dto = new VoicePrintSaveDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setSourceName("测试称呼_audioBase64");
        dto.setIntroduce("这是使用audioBase64保存的声纹");
        dto.setAudioBase64(mockOpusBase64);

        VoicePrintRespDTO result = voicePrintService.save(getTestUserId(), dto);

        Assertions.assertNotNull(result, "返回结果不应为空");
        Assertions.assertNotNull(result.getId(), "声纹ID不应为空");
        Assertions.assertNotNull(result.getAudioId(), "音频ID不应为空");
        Assertions.assertEquals("测试称呼_audioBase64", result.getSourceName(), "称呼应一致");

        log.info("声纹保存成功（audioBase64）: id={}, audioId={}, sourceName={}",
                result.getId(), result.getAudioId(), result.getSourceName());
    }

    @Test
    @Order(1)
    @DisplayName("声纹录音 - audioBase64格式错误时抛出异常")
    void testSaveVoicePrintWithInvalidAudioBase64() {
        ensureTestData();
        log.info("=== 测试：audioBase64格式错误时抛出异常 ===");

        VoicePrintSaveDTO dto = new VoicePrintSaveDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setSourceName("测试称呼_非法audioBase64");
        dto.setAudioBase64("这不是有效的Base64编码!!!");

        Assertions.assertThrows(RenException.class, () -> {
            voicePrintService.save(getTestUserId(), dto);
        }, "无效的Base64应该抛出异常");

        log.info("异常捕获正确");
    }

    @Test
    @Order(2)
    @DisplayName("声纹录音 - 获取声纹列表")
    void testListVoicePrint() {
        ensureTestData();
        log.info("=== 测试：获取声纹列表 ===");

        List<VoicePrintRespDTO> list = voicePrintService.list(getTestUserId(), TEST_VERIFY_CODE);

        Assertions.assertNotNull(list, "列表不应为空");
        Assertions.assertTrue(list.size() >= 1, "列表至少应该有1条记录");

        boolean found = list.stream().anyMatch(vp -> "测试称呼1".equals(vp.getSourceName()));
        Assertions.assertTrue(found, "列表中应包含刚才保存的声纹");

        log.info("声纹列表获取成功: count={}", list.size());
    }

    @Test
    @Order(3)
    @DisplayName("声纹录音 - 更新声纹")
    void testUpdateVoicePrint() {
        ensureTestData();
        log.info("=== 测试：更新声纹 ===");

        // 先获取一条声纹
        List<VoicePrintRespDTO> list = voicePrintService.list(getTestUserId(), TEST_VERIFY_CODE);
        Assertions.assertTrue(list.size() >= 1, "需要有已存在的声纹记录");
        VoicePrintRespDTO existing = list.stream()
                .filter(vp -> "测试称呼1".equals(vp.getSourceName()))
                .findFirst()
                .orElseThrow();

        VoicePrintUpdateDTO dto = new VoicePrintUpdateDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setId(existing.getId());
        dto.setSourceName("测试称呼1_已更新");
        dto.setIntroduce("这是更新后的描述");

        VoicePrintRespDTO result = voicePrintService.update(getTestUserId(), dto);

        Assertions.assertEquals("测试称呼1_已更新", result.getSourceName(), "称呼应已更新");
        Assertions.assertEquals("这是更新后的描述", result.getIntroduce(), "描述应已更新");

        log.info("声纹更新成功: id={}", result.getId());
    }

    @Test
    @Order(4)
    @DisplayName("声纹录音 - 删除声纹")
    void testDeleteVoicePrint() {
        ensureTestData();
        log.info("=== 测试：删除声纹 ===");

        // 先获取一条声纹
        List<VoicePrintRespDTO> list = voicePrintService.list(getTestUserId(), TEST_VERIFY_CODE);
        Assertions.assertTrue(list.size() >= 1, "需要有已存在的声纹记录");
        VoicePrintRespDTO toDelete = list.stream()
                .filter(vp -> "测试称呼1_已更新".equals(vp.getSourceName()))
                .findFirst()
                .orElseThrow();

        voicePrintService.delete(getTestUserId(), TEST_VERIFY_CODE, toDelete.getId());

        // 验证删除
        List<VoicePrintRespDTO> listAfter = voicePrintService.list(getTestUserId(), TEST_VERIFY_CODE);
        boolean stillExists = listAfter.stream().anyMatch(vp -> toDelete.getId().equals(vp.getId()));
        Assertions.assertFalse(stillExists, "声纹应该已被删除");

        log.info("声纹删除成功: id={}", toDelete.getId());
    }

    @Test
    @Order(5)
    @DisplayName("声纹录音 - 设备不存在时抛出异常")
    void testVoicePrintWithInvalidDevice() {
        log.info("=== 测试：设备不存在时抛出异常 ===");

        VoicePrintSaveDTO dto = new VoicePrintSaveDTO();
        dto.setVerifyCode("INVALID_CODE_XXXXX");
        dto.setSourceName("无效测试");

        Assertions.assertThrows(RenException.class, () -> {
            voicePrintService.save(getTestUserId(), dto);
        }, "设备不存在应该抛出异常");

        log.info("异常捕获正确");
    }

    // ==================== 声音克隆测试 ====================

    @Test
    @Order(10)
    @DisplayName("声音克隆 - 保存声音克隆")
    void testSaveVoiceClone() {
        ensureTestData();
        log.info("=== 测试：保存声音克隆 ===");

        VoiceCloneSaveDTO dto = new VoiceCloneSaveDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setName("测试声音克隆");
        dto.setModelId("DEFAULT_MODEL_ID"); // 注意：可能需要有效的模型ID
        dto.setLanguages("zh-CN");

        VoiceCloneRespDTO result = voiceCloneService.save(getTestUserId(), dto);

        Assertions.assertNotNull(result, "返回结果不应为空");
        Assertions.assertNotNull(result.getId(), "声音克隆ID不应为空");
        Assertions.assertEquals("测试声音克隆", result.getName(), "名称应一致");
        Assertions.assertEquals("zh-CN", result.getLanguages(), "语言应一致");
        Assertions.assertEquals(0, result.getTrainStatus(), "训练状态应为0（待训练）");

        log.info("声音克隆保存成功: id={}, name={}", result.getId(), result.getName());
    }

    @Test
    @Order(11)
    @DisplayName("声音克隆 - 获取声音克隆列表")
    void testListVoiceClone() {
        ensureTestData();
        log.info("=== 测试：获取声音克隆列表 ===");

        List<VoiceCloneRespDTO> list = voiceCloneService.list(getTestUserId(), TEST_VERIFY_CODE);

        Assertions.assertNotNull(list, "列表不应为空");
        Assertions.assertTrue(list.size() >= 1, "列表至少应该有1条记录");

        log.info("声音克隆列表获取成功: count={}", list.size());
    }

    @Test
    @Order(12)
    @DisplayName("声音克隆 - 更新声音克隆")
    void testUpdateVoiceClone() {
        ensureTestData();
        log.info("=== 测试：更新声音克隆 ===");

        // 先获取一条声音克隆
        List<VoiceCloneRespDTO> list = voiceCloneService.list(getTestUserId(), TEST_VERIFY_CODE);
        Assertions.assertTrue(list.size() >= 1, "需要有已存在的声音克隆记录");
        VoiceCloneRespDTO existing = list.get(0);

        VoiceCloneUpdateDTO dto = new VoiceCloneUpdateDTO();
        dto.setId(existing.getId());
        dto.setName("测试声音克隆_已更新");
        dto.setLanguages("en-US");

        VoiceCloneRespDTO result = voiceCloneService.update(getTestUserId(), dto);

        Assertions.assertEquals("测试声音克隆_已更新", result.getName(), "名称应已更新");

        log.info("声音克隆更新成功: id={}", result.getId());
    }

    @Test
    @Order(13)
    @DisplayName("声音克隆 - 无权修改他人声音克隆")
    void testUpdateVoiceCloneUnauthorized() {
        ensureTestData();
        log.info("=== 测试：无权修改他人声音克隆 ===");

        VoiceCloneUpdateDTO dto = new VoiceCloneUpdateDTO();
        dto.setId("SOME_OTHER_USER_CLONE_ID");
        dto.setName("不应成功的更新");

        Assertions.assertThrows(RenException.class, () -> {
            voiceCloneService.update(99999L, dto); // 使用不同的用户ID
        }, "无权修改应该抛出异常");

        log.info("异常捕获正确");
    }

    @Test
    @Order(14)
    @DisplayName("声音克隆 - 删除声音克隆")
    void testDeleteVoiceClone() {
        ensureTestData();
        log.info("=== 测试：删除声音克隆 ===");

        // 先获取一条声音克隆
        List<VoiceCloneRespDTO> list = voiceCloneService.list(getTestUserId(), TEST_VERIFY_CODE);
        Assertions.assertTrue(list.size() >= 1, "需要有已存在的声音克隆记录");
        VoiceCloneRespDTO toDelete = list.stream()
                .filter(vc -> "测试声音克隆_已更新".equals(vc.getName()))
                .findFirst()
                .orElse(list.get(0));

        voiceCloneService.delete(getTestUserId(), TEST_VERIFY_CODE, toDelete.getId());

        // 验证删除（查询列表不应包含该记录，或者如果被删除则列表变小）
        List<VoiceCloneRespDTO> listAfter = voiceCloneService.list(getTestUserId(), TEST_VERIFY_CODE);
        boolean stillExists = listAfter.stream().anyMatch(vc -> toDelete.getId().equals(vc.getId()));
        Assertions.assertFalse(stillExists, "声音克隆应该已被删除");

        log.info("声音克隆删除成功: id={}", toDelete.getId());
    }

    @Test
    @Order(15)
    @DisplayName("声音克隆 - 设备不存在时抛出异常")
    void testVoiceCloneWithInvalidDevice() {
        log.info("=== 测试：声音克隆 - 设备不存在时抛出异常 ===");

        VoiceCloneSaveDTO dto = new VoiceCloneSaveDTO();
        dto.setVerifyCode("INVALID_CODE_XXXXX");
        dto.setName("无效测试");
        dto.setModelId("DEFAULT_MODEL_ID");

        Assertions.assertThrows(RenException.class, () -> {
            voiceCloneService.save(getTestUserId(), dto);
        }, "设备不存在应该抛出异常");

        log.info("异常捕获正确");
    }

    // ==================== 清理测试数据 ====================

    @Test
    @Order(100)
    @DisplayName("清理测试数据")
    void testCleanup() {
        log.info("=== 清理测试数据 ===");

        // 删除设备（会级联删除关联数据）
        if (testDeviceId != null) {
            deviceDao.deleteById(testDeviceId);
            log.info("已删除测试设备: {}", testDeviceId);
        }

        // 删除智能体
        if (testAgentId != null) {
            try {
                agentDao.deleteById(testAgentId);
                log.info("已删除测试智能体: {}", testAgentId);
            } catch (Exception e) {
                log.warn("删除智能体失败（可能已被级联删除）: {}", e.getMessage());
            }
        }

        setupDone = false;
        log.info("测试数据清理完成");
    }
}
