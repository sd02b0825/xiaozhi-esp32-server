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
import xiaozhi.modules.zs.dto.DeviceBindAgentDTO;
import xiaozhi.modules.zs.dto.DeviceBindAgentRespDTO;
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
}
