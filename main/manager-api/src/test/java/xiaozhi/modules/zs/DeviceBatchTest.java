package xiaozhi.modules.zs;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import lombok.extern.slf4j.Slf4j;
import xiaozhi.modules.device.dao.DeviceDao;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.zs.dto.DeviceBatchAddDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddDTO.DeviceItemDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO;
import xiaozhi.modules.zs.service.DeviceBatchService;

@Slf4j
@SpringBootTest
@ActiveProfiles("dev")
@DisplayName("批量设备录入测试")
public class DeviceBatchTest {

    /** 测试用户ID */
    protected static final Long TEST_USER_ID = 2019982586052349954L;

    @Autowired
    private DeviceBatchService deviceBatchService;

    @Autowired
    private DeviceDao deviceDao;

    @Test
    @DisplayName("测试批量录入单个设备")
    public void testBatchAddSingleDevice() {
        log.info("开始测试批量录入单个设备...");

        DeviceBatchAddDTO dto = new DeviceBatchAddDTO();
        List<DeviceItemDTO> devices = new ArrayList<>();

        DeviceItemDTO item = new DeviceItemDTO();
        item.setMacAddress("AA:BB:CC:DD:EE:FF");
        item.setVerifyCode("123456");
        devices.add(item);

        dto.setDevices(devices);

        DeviceBatchAddRespDTO result = deviceBatchService.batchAddDevice(dto);

        log.info("结果: successCount={}, failCount={}", result.getSuccessCount(), result.getFailCount());
        Assertions.assertEquals(1, result.getSuccessCount(), "应该成功录入1个设备");
        Assertions.assertEquals(0, result.getFailCount(), "不应该有失败的设备");

        // 清理测试数据
        //deviceDao.deleteById("AA:BB:CC:DD:EE:FF");
        log.info("测试完成，已清理测试数据");
    }

    @Test
    @DisplayName("测试批量录入多个设备")
    public void testBatchAddMultipleDevices() {
        log.info("开始测试批量录入多个设备...");

        DeviceBatchAddDTO dto = new DeviceBatchAddDTO();
        List<DeviceItemDTO> devices = new ArrayList<>();

        for (int i = 1; i <= 3; i++) {
            DeviceItemDTO item = new DeviceItemDTO();
            item.setMacAddress(String.format("11:22:33:44:55:%02d", i));
            item.setVerifyCode(String.format("65432%d", i));
            devices.add(item);
        }

        dto.setDevices(devices);

        DeviceBatchAddRespDTO result = deviceBatchService.batchAddDevice(dto);

        log.info("结果: successCount={}, failCount={}", result.getSuccessCount(), result.getFailCount());
        Assertions.assertEquals(3, result.getSuccessCount(), "应该成功录入3个设备");
        Assertions.assertEquals(0, result.getFailCount(), "不应该有失败的设备");

        // 清理测试数据
        for (int i = 1; i <= 3; i++) {
            deviceDao.deleteById(String.format("11:22:33:44:55:%02d", i));
        }
        log.info("测试完成，已清理测试数据");
    }

    @Test
    @DisplayName("测试重复设备录入")
    public void testDuplicateDeviceEntry() {
        log.info("开始测试重复设备录入...");

        String macAddress = "22:33:44:55:66:77";

        // 先录入一个设备
        DeviceBatchAddDTO dto1 = new DeviceBatchAddDTO();
        List<DeviceItemDTO> devices1 = new ArrayList<>();
        DeviceItemDTO item1 = new DeviceItemDTO();
        item1.setMacAddress(macAddress);
        item1.setVerifyCode("111111");
        devices1.add(item1);
        dto1.setDevices(devices1);
        deviceBatchService.batchAddDevice(dto1);

        // 再次录入同一个设备
        DeviceBatchAddDTO dto2 = new DeviceBatchAddDTO();
        List<DeviceItemDTO> devices2 = new ArrayList<>();
        DeviceItemDTO item2 = new DeviceItemDTO();
        item2.setMacAddress(macAddress);
        item2.setVerifyCode("222222");
        devices2.add(item2);
        dto2.setDevices(devices2);

        DeviceBatchAddRespDTO result = deviceBatchService.batchAddDevice(dto2);

        log.info("结果: successCount={}, failCount={}", result.getSuccessCount(), result.getFailCount());
        Assertions.assertEquals(0, result.getSuccessCount(), "重复录入应该失败");
        Assertions.assertEquals(1, result.getFailCount(), "应该有1个失败的设备");
        Assertions.assertEquals("设备已存在", result.getFailList().get(0).getReason(), "失败原因应该是设备已存在");

        // 清理测试数据
        deviceDao.deleteById(macAddress);
        log.info("测试完成，已清理测试数据");
    }

    @Test
    @DisplayName("测试部分成功部分失败")
    public void testPartialSuccess() {
        log.info("开始测试部分成功部分失败...");

        DeviceBatchAddDTO dto = new DeviceBatchAddDTO();
        List<DeviceItemDTO> devices = new ArrayList<>();

        // 第一个设备 - 新设备，应该成功
        DeviceItemDTO item1 = new DeviceItemDTO();
        item1.setMacAddress("33:44:55:66:77:01");
        item1.setVerifyCode("333333");
        devices.add(item1);

        // 第二个设备 - 重复设备，应该失败
        DeviceItemDTO item2 = new DeviceItemDTO();
        item2.setMacAddress("33:44:55:66:77:01");
        item2.setVerifyCode("444444");
        devices.add(item2);

        // 第三个设备 - 新设备，应该成功
        DeviceItemDTO item3 = new DeviceItemDTO();
        item3.setMacAddress("33:44:55:66:77:02");
        item3.setVerifyCode("555555");
        devices.add(item3);

        dto.setDevices(devices);

        DeviceBatchAddRespDTO result = deviceBatchService.batchAddDevice(dto);

        log.info("结果: successCount={}, failCount={}", result.getSuccessCount(), result.getFailCount());
        Assertions.assertEquals(2, result.getSuccessCount(), "应该有2个设备成功");
        Assertions.assertEquals(1, result.getFailCount(), "应该有1个设备失败");

        // 清理测试数据
        deviceDao.deleteById("33:44:55:66:77:01");
        deviceDao.deleteById("33:44:55:66:77:02");
        log.info("测试完成，已清理测试数据");
    }

    @Test
    @DisplayName("测试设备信息正确保存")
    public void testDeviceInfoSavedCorrectly() {
        log.info("开始测试设备信息正确保存...");

        String macAddress = "55:66:77:88:99:00";
        String verifyCode = "998877";
        String board = "ESP32-S3-BOX";

        DeviceBatchAddDTO dto = new DeviceBatchAddDTO();
        List<DeviceItemDTO> devices = new ArrayList<>();
        DeviceItemDTO item = new DeviceItemDTO();
        item.setMacAddress(macAddress);
        item.setVerifyCode(verifyCode);
        devices.add(item);
        dto.setDevices(devices);

        deviceBatchService.batchAddDevice(dto);

        // 验证数据库中的数据
        DeviceEntity savedDevice = deviceDao.selectById(macAddress);
        Assertions.assertNotNull(savedDevice, "设备应该被保存到数据库");
        Assertions.assertEquals(macAddress, savedDevice.getMacAddress(), "MAC地址应该一致");
        Assertions.assertEquals(verifyCode, savedDevice.getVerifyCode(), "验证码应该一致");
        Assertions.assertEquals(board, savedDevice.getBoard(), "设备型号应该一致");
        Assertions.assertEquals(TEST_USER_ID, savedDevice.getUserId(), "用户ID应该一致");

        log.info("设备信息验证通过: {}", savedDevice);

        // 清理测试数据
        deviceDao.deleteById(macAddress);
        log.info("测试完成，已清理测试数据");
    }
}
