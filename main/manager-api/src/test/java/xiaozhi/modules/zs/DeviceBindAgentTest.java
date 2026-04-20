package xiaozhi.modules.zs;

import java.util.Date;

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
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;
import xiaozhi.modules.zs.service.DeviceBindAgentService;

@Slf4j
@SpringBootTest
@ActiveProfiles("dev")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@DisplayName("设备绑定智能体接口测试")
public class DeviceBindAgentTest {

    /** 测试用户ID */
    protected static final Long TEST_USER_ID = 2019982586052349954L;

    private static final String TEST_MAC = "AA:BB:CC:DD:EE:10";
    private static final String TEST_VERIFY_CODE = "998877";
    private static String testAgentId;
    private static boolean setupDone = false;

    @Autowired
    private DeviceBindAgentService deviceBindAgentService;

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
     * 前置：创建未绑定智能体的测试设备
     */
    private void ensureTestData() {
        if (setupDone) {
            return;
        }

        Long userId = TEST_USER_ID;
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

        setupDone = true;
    }

    // ==================== 设备绑定智能体测试 ====================

    @Test
    @Order(1)
    @DisplayName("设备绑定智能体 - 正常绑定")
    void testBindAgentSuccess() {

        String agentName = "TestAgent_Bind_" + System.currentTimeMillis();
        log.info("=== 测试：设备绑定智能体 - 正常绑定 ===");

        DeviceBindAgentDTO dto = new DeviceBindAgentDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setAgentName(agentName);

        DeviceBindAgentRespDTO result = deviceBindAgentService.bindAgent(TEST_USER_ID, dto);

        Assertions.assertNotNull(result, "返回结果不应为空");
        Assertions.assertNotNull(result.getAgentId(), "智能体ID不应为空");
        Assertions.assertEquals(agentName, result.getAgentName(), "智能体名称应一致");
        Assertions.assertEquals(TEST_MAC, result.getMacAddress(), "MAC地址应一致");

        testAgentId = result.getAgentId();
        log.info("设备绑定智能体成功: agentId={}, agentName={}, mac={}",
                result.getAgentId(), result.getAgentName(), result.getMacAddress());
    }

    @Test
    @Order(2)
    @DisplayName("设备绑定智能体 - 设备不存在")
    void testBindAgentWithInvalidDevice() {
        log.info("=== 测试：设备绑定智能体 - 设备不存在 ===");

        DeviceBindAgentDTO dto = new DeviceBindAgentDTO();
        dto.setVerifyCode("INVALID_CODE_XXXXX");
        dto.setAgentName("无效设备测试智能体");

        RenException exception = Assertions.assertThrows(RenException.class, () -> {
            deviceBindAgentService.bindAgent(getTestUserId(), dto);
        }, "设备不存在应该抛出异常");

        Assertions.assertTrue(exception.getMessage().contains("设备不存在"), "异常信息应包含'设备不存在'");

        log.info("异常捕获正确: {}", exception.getMessage());
    }

    @Test
    @Order(3)
    @DisplayName("设备绑定智能体 - 设备已绑定其他智能体")
    void testBindAgentWithAlreadyBoundDevice() {
        ensureTestData();
        log.info("=== 测试：设备绑定智能体 - 设备已绑定其他智能体 ===");

        // 设备已绑定（上一个测试已绑定），再次绑定应该报错
        DeviceBindAgentDTO dto = new DeviceBindAgentDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setAgentName("重复绑定测试智能体");

        RenException exception = Assertions.assertThrows(RenException.class, () -> {
            deviceBindAgentService.bindAgent(getTestUserId(), dto);
        }, "设备已绑定应该抛出异常");

        Assertions.assertTrue(exception.getMessage().contains("已绑定"), "异常信息应包含'已绑定'");

        log.info("异常捕获正确: {}", exception.getMessage());
    }

    @Test
    @Order(4)
    @DisplayName("设备绑定智能体 - 不同用户无法绑定同一设备")
    void testBindAgentWithDifferentUser() {
        ensureTestData();
        Long differentUserId = 99999L;
        log.info("=== 测试：设备绑定智能体 - 不同用户无法绑定同一设备 ===");

        // 创建另一个用户的设备
        DeviceEntity otherDevice = new DeviceEntity();
        otherDevice.setId("OTHER_MAC_20");
        otherDevice.setMacAddress("11:22:33:44:55:20");
        otherDevice.setVerifyCode("OTHER_VERIFY_20");
        otherDevice.setBoard("esp32-s3-box");
        otherDevice.setUserId(differentUserId);
        otherDevice.setCreator(differentUserId);
        otherDevice.setCreateDate(new Date());
        otherDevice.setUpdater(differentUserId);
        otherDevice.setUpdateDate(new Date());
        otherDevice.setAutoUpdate(1);
        deviceDao.insert(otherDevice);
        log.info("[Setup] 创建其他用户的设备: mac={}, verifyCode={}", otherDevice.getMacAddress(), otherDevice.getVerifyCode());

        // 用当前用户ID去绑定其他用户的设备验证码，应该报错
        DeviceBindAgentDTO dto = new DeviceBindAgentDTO();
        dto.setVerifyCode(otherDevice.getVerifyCode());
        dto.setAgentName("无权限绑定测试");

        RenException exception = Assertions.assertThrows(RenException.class, () -> {
            deviceBindAgentService.bindAgent(getTestUserId(), dto);
        }, "不同用户设备验证码应该抛出异常");

        Assertions.assertTrue(exception.getMessage().contains("设备不存在"), "异常信息应包含'设备不存在'");

        // 清理
        deviceDao.deleteById(otherDevice.getId());
        log.info("异常捕获正确，测试数据已清理");
    }

    // ==================== 清理测试数据 ====================

    @Test
    @Order(100)
    @DisplayName("清理测试数据")
    void testCleanup() {
        log.info("=== 清理测试数据 ===");

        Long userId = getTestUserId();
        // 删除设备
        DeviceEntity device = deviceDao.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<DeviceEntity>()
                        .eq(DeviceEntity::getVerifyCode, TEST_VERIFY_CODE));
        if (device != null) {
            device.setAgentId(null); // 解绑智能体
            device.setUpdater(userId);
            device.setUpdateDate(new Date());
            deviceDao.updateById(device);
            log.info("已解绑设备: {}", device.getId());
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
