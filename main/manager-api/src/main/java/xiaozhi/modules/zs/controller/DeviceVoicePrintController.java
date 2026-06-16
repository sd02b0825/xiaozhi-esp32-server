package xiaozhi.modules.zs.controller;

import java.util.List;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.zs.dto.VoicePrintRespDTO;
import xiaozhi.modules.zs.dto.VoicePrintSaveDTO;
import xiaozhi.modules.zs.dto.VoicePrintUpdateDTO;
import xiaozhi.modules.zs.service.VoicePrintService;

@Tag(name = "设备声纹管理")
@RestController
@RequestMapping("/zs/voice")
public class DeviceVoicePrintController {

    private final VoicePrintService voicePrintService;

    public DeviceVoicePrintController(VoicePrintService voicePrintService) {
        this.voicePrintService = voicePrintService;
    }

    @PostMapping("/voiceprint")
    @Operation(summary = "保存声纹录音")
    @RequiresPermissions("sys:role:normal")
    public Result<VoicePrintRespDTO> saveVoicePrint(@RequestBody @Valid VoicePrintSaveDTO dto) {
        UserDetail user = SecurityUser.getUser();
        VoicePrintRespDTO result = voicePrintService.save(user.getId(), dto);
        return new Result<VoicePrintRespDTO>().ok(result);
    }

    @GetMapping("/voiceprint")
    @Operation(summary = "获取声纹列表")
    @RequiresPermissions("sys:role:normal")
    public Result<List<VoicePrintRespDTO>> listVoicePrint(@RequestParam String verifyCode) {
        UserDetail user = SecurityUser.getUser();
        List<VoicePrintRespDTO> result = voicePrintService.list(user.getId(), verifyCode);
        return new Result<List<VoicePrintRespDTO>>().ok(result);
    }

    @PutMapping("/voiceprint")
    @Operation(summary = "更新声纹录音")
    @RequiresPermissions("sys:role:normal")
    public Result<VoicePrintRespDTO> updateVoicePrint(@RequestBody @Valid VoicePrintUpdateDTO dto) {
        UserDetail user = SecurityUser.getUser();
        VoicePrintRespDTO result = voicePrintService.update(user.getId(), dto);
        return new Result<VoicePrintRespDTO>().ok(result);
    }

    @DeleteMapping("/voiceprint")
    @Operation(summary = "删除声纹录音")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> deleteVoicePrint(@RequestParam String verifyCode, @RequestParam String voiceId) {
        UserDetail user = SecurityUser.getUser();
        voicePrintService.delete(user.getId(), verifyCode, voiceId);
        return new Result<Void>().ok(null);
    }
}
