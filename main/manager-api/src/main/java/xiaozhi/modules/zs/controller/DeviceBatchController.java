package xiaozhi.modules.zs.controller;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.zs.dto.DeviceBatchAddDTO;
import xiaozhi.modules.zs.dto.DeviceBatchAddRespDTO;
import xiaozhi.modules.zs.service.DeviceBatchService;

@Tag(name = "批量设备管理")
@RestController
@RequestMapping("/zs/device")
public class DeviceBatchController {

    private final DeviceBatchService deviceBatchService;

    public DeviceBatchController(DeviceBatchService deviceBatchService) {
        this.deviceBatchService = deviceBatchService;
    }

    @PostMapping("/batch-add")
    @Operation(summary = "批量录入设备")
    @RequiresPermissions("sys:role:normal")
    public Result<DeviceBatchAddRespDTO> batchAddDevice(@RequestBody @Valid DeviceBatchAddDTO dto) {
        DeviceBatchAddRespDTO result = deviceBatchService.batchAddDevice(dto);
        return new Result<DeviceBatchAddRespDTO>().ok(result);
    }
}
