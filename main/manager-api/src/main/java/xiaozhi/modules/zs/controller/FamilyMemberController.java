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
import lombok.RequiredArgsConstructor;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.zs.dto.FamilyMemberBatchSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberRespDTO;
import xiaozhi.modules.zs.dto.FamilyMemberSaveDTO;
import xiaozhi.modules.zs.dto.FamilyMemberUpdateDTO;
import xiaozhi.modules.zs.service.FamilyMemberService;

@Tag(name = "亲属管理")
@RestController
@RequestMapping("/zs/family")
@RequiredArgsConstructor
public class FamilyMemberController {

    private final FamilyMemberService familyMemberService;

    @PostMapping
    @Operation(summary = "添加亲属")
    @RequiresPermissions("sys:role:normal")
    public Result<FamilyMemberRespDTO> save(@RequestBody @Valid FamilyMemberSaveDTO dto) {
        UserDetail user = SecurityUser.getUser();
        FamilyMemberRespDTO result = familyMemberService.save(user.getId(), dto);
        return new Result<FamilyMemberRespDTO>().ok(result);
    }

    @PostMapping("/batch")
    @Operation(summary = "批量添加亲属")
    @RequiresPermissions("sys:role:normal")
    public Result<List<FamilyMemberRespDTO>> saveBatch(@RequestBody @Valid FamilyMemberBatchSaveDTO dto) {
        UserDetail user = SecurityUser.getUser();
        List<FamilyMemberRespDTO> result = familyMemberService.saveBatch(user.getId(), dto);
        return new Result<List<FamilyMemberRespDTO>>().ok(result);
    }

    @GetMapping
    @Operation(summary = "获取亲属列表")
    @RequiresPermissions("sys:role:normal")
    public Result<List<FamilyMemberRespDTO>> list(@RequestParam String verifyCode) {
        UserDetail user = SecurityUser.getUser();
        List<FamilyMemberRespDTO> result = familyMemberService.list(user.getId(), verifyCode);
        return new Result<List<FamilyMemberRespDTO>>().ok(result);
    }

    @PutMapping
    @Operation(summary = "更新亲属")
    @RequiresPermissions("sys:role:normal")
    public Result<FamilyMemberRespDTO> update(@RequestBody @Valid FamilyMemberUpdateDTO dto) {
        UserDetail user = SecurityUser.getUser();
        FamilyMemberRespDTO result = familyMemberService.update(user.getId(), dto);
        return new Result<FamilyMemberRespDTO>().ok(result);
    }

    @DeleteMapping
    @Operation(summary = "删除亲属")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> delete(@RequestParam String verifyCode, @RequestParam Long memberId) {
        UserDetail user = SecurityUser.getUser();
        familyMemberService.delete(user.getId(), verifyCode, memberId);
        return new Result<Void>().ok(null);
    }
}
