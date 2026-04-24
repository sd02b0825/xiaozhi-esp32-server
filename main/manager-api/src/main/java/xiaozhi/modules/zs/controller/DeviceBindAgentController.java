package xiaozhi.modules.zs.controller;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PathVariable;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;
import xiaozhi.modules.zs.dto.DeviceUpdateAgentDTO;
import xiaozhi.modules.zs.service.DeviceBindAgentService;

@Tag(name = "设备绑定管理")
@RestController
@RequestMapping("/zs/device")
public class DeviceBindAgentController {

    private final DeviceBindAgentService deviceBindAgentService;

    public DeviceBindAgentController(DeviceBindAgentService deviceBindAgentService) {
        this.deviceBindAgentService = deviceBindAgentService;
    }

    @PostMapping("/bind-agent")
    @Operation(summary = "设备绑定智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<DeviceBindAgentRespDTO> bindAgent(@RequestBody @Valid DeviceBindAgentDTO dto) {
        UserDetail user = SecurityUser.getUser();
        DeviceBindAgentRespDTO result = deviceBindAgentService.bindAgent(user.getId(), dto);
        return new Result<DeviceBindAgentRespDTO>().ok(result);
    }

    @PutMapping("/bind-agent/{id}")
    @Operation(summary = "修改设备智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<DeviceBindAgentRespDTO> updateAgent(@PathVariable("id") String id,
            @RequestBody @Valid DeviceUpdateAgentDTO dto) {
        UserDetail user = SecurityUser.getUser();
        DeviceBindAgentRespDTO result = deviceBindAgentService.updateAgent(user.getId(), id, dto);
        return new Result<DeviceBindAgentRespDTO>().ok(result);
    }

    @DeleteMapping("/bind-agent/{id}")
    @Operation(summary = "删除设备智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> deleteAgent(@PathVariable("id") String id) {
        UserDetail user = SecurityUser.getUser();
        deviceBindAgentService.deleteAgent(user.getId(), id);
        return new Result<Void>().ok(null);
    }
}
