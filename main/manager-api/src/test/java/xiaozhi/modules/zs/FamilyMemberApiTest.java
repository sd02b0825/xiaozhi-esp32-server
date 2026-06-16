package xiaozhi.modules.zs;

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
import xiaozhi.modules.zs.dto.FamilyMemberRespDTO;
import xiaozhi.modules.zs.dto.FamilyMemberSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberUpdateDTO;
import xiaozhi.modules.zs.service.FamilyMemberService;

@Slf4j
@SpringBootTest
@ActiveProfiles("dev")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@DisplayName("亲属管理接口测试")
public class FamilyMemberApiTest {

    /** 测试用户ID */
    protected static final Long TEST_USER_ID = 2019982586052349954L;

    private static final String TEST_MAC = "AA:BB:CC:DD:EE:31";
    private static final String TEST_VERIFY_CODE = "FAMILY124";
    private static String testAgentId;
    private static Integer testMemberId;
    private static boolean setupDone = false;

    @Autowired
    private FamilyMemberService familyMemberService;

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
        String agentName = "TestAgent_Family_" + System.currentTimeMillis();

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

    // ==================== 亲属管理测试 ====================

    @Test
    @Order(1)
    @DisplayName("亲属管理 - 添加亲属")
    void testSaveFamilyMember() {
        ensureTestData();
        log.info("=== 测试：添加亲属 ===");

        FamilyMemberSaveDTO dto = new FamilyMemberSaveDTO();
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setName("张三");
        dto.setPhone("13800138000");
        dto.setRemark("家庭成员测试");

        FamilyMemberRespDTO result = familyMemberService.save(getTestUserId(), dto);

        Assertions.assertNotNull(result, "返回结果不应为空");
        Assertions.assertNotNull(result.getId(), "亲属ID不应为空");
        Assertions.assertEquals("张三", result.getName(), "姓名应一致");
        Assertions.assertEquals("13800138000", result.getPhone(), "手机号应一致");
        Assertions.assertEquals("家庭成员测试", result.getRemark(), "备注应一致");
        Assertions.assertNotNull(result.getDeviceId(), "设备ID不应为空");
        Assertions.assertNotNull(result.getAgentId(), "智能体ID不应为空");

        testMemberId = result.getId();
        log.info("亲属添加成功: id={}, name={}, phone={}", result.getId(), result.getName(), result.getPhone());
    }

    @Test
    @Order(2)
    @DisplayName("亲属管理 - 获取亲属列表")
    void testListFamilyMember() {
        ensureTestData();
        log.info("=== 测试：获取亲属列表 ===");

        List<FamilyMemberRespDTO> list = familyMemberService.list(getTestUserId(), TEST_VERIFY_CODE);

        Assertions.assertNotNull(list, "列表不应为空");
        Assertions.assertTrue(list.size() >= 1, "列表至少应该有1条记录");

        boolean found = list.stream().anyMatch(m -> "张三".equals(m.getName()));
        Assertions.assertTrue(found, "列表中应包含刚才添加的亲属");

        log.info("亲属列表获取成功: count={}", list.size());
    }

    @Test
    @Order(3)
    @DisplayName("亲属管理 - 更新亲属")
    void testUpdateFamilyMember() {
        ensureTestData();
        log.info("=== 测试：更新亲属 ===");

        Assertions.assertNotNull(testMemberId, "需要先添加亲属");

        FamilyMemberUpdateDTO dto = new FamilyMemberUpdateDTO();
        dto.setId(testMemberId);
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setName("张三_已更新");
        dto.setPhone("13900139000");
        dto.setRemark("更新后的备注");

        FamilyMemberRespDTO result = familyMemberService.update(getTestUserId(), dto);

        Assertions.assertEquals("张三_已更新", result.getName(), "姓名应已更新");
        Assertions.assertEquals("13900139000", result.getPhone(), "手机号应已更新");
        Assertions.assertEquals("更新后的备注", result.getRemark(), "备注应已更新");

        log.info("亲属更新成功: id={}", result.getId());
    }

    @Test
    @Order(4)
    @DisplayName("亲属管理 - 设备不存在时抛出异常")
    void testFamilyMemberWithInvalidDevice() {
        log.info("=== 测试：设备不存在时抛出异常 ===");

        FamilyMemberSaveDTO dto = new FamilyMemberSaveDTO();
        dto.setVerifyCode("INVALID_CODE_XXXXX");
        dto.setName("无效测试");
        dto.setPhone("10000000000");

        Assertions.assertThrows(RenException.class, () -> {
            familyMemberService.save(getTestUserId(), dto);
        }, "设备不存在应该抛出异常");

        log.info("异常捕获正确");
    }

    @Test
    @Order(5)
    @DisplayName("亲属管理 - 更新不存在的亲属")
    void testUpdateNonExistentMember() {
        ensureTestData();
        log.info("=== 测试：更新不存在的亲属 ===");

        FamilyMemberUpdateDTO dto = new FamilyMemberUpdateDTO();
        dto.setId(999999);
        dto.setVerifyCode(TEST_VERIFY_CODE);
        dto.setName("不存在的亲属");
        dto.setPhone("10000000000");

        Assertions.assertThrows(RenException.class, () -> {
            familyMemberService.update(getTestUserId(), dto);
        }, "亲属不存在应该抛出异常");

        log.info("异常捕获正确");
    }

    @Test
    @Order(5)
    @DisplayName("亲属管理 - 删除不存在的亲属")
    void testDeleteNonExistentMember() {
        ensureTestData();
        log.info("=== 测试：删除不存在的亲属 ===");

        Assertions.assertThrows(RenException.class, () -> {
            familyMemberService.delete(getTestUserId(), TEST_VERIFY_CODE, 999999);
        }, "亲属不存在应该抛出异常");

        log.info("异常捕获正确");
    }

    // ==================== 保留测试数据 ====================

    @Test
    @Order(100)
    @DisplayName("保留测试数据（不删除，便于查看）")
    void testPreserveData() {
        log.info("=== 保留测试数据 ===");
        log.info("测试设备: mac={}, verifyCode={}", TEST_MAC, TEST_VERIFY_CODE);
        log.info("测试智能体: agentId={}", testAgentId);
        log.info("测试亲属ID: memberId={}", testMemberId);
        log.info("请前往数据库查看 ai_family_member 表验证数据");
        // 不删除任何数据，便于查看
    }
}
