package xiaozhi.modules.zs.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.TokenDTO;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.password.PasswordUtils;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.sys.dto.SysUserDTO;
import xiaozhi.modules.sys.service.SysUserService;
import xiaozhi.modules.zs.dto.ZsLoginDTO;

@Tag(name = "ZS认证")
@RestController
@RequestMapping("/zs/auth")
@RequiredArgsConstructor
public class ZsAuthController {

    private final SysUserService sysUserService;
    private final SysUserTokenService sysUserTokenService;

    @PostMapping("/token")
    @Operation(summary = "获取登录Token")
    public Result<TokenDTO> token(@RequestBody @Valid ZsLoginDTO dto) {
        SysUserDTO userDTO = sysUserService.getByUsername(dto.getUsername());
        if (userDTO == null) {
            throw new RenException(ErrorCode.ACCOUNT_PASSWORD_ERROR);
        }

        if (!PasswordUtils.matches(dto.getPassword(), userDTO.getPassword())) {
            throw new RenException(ErrorCode.ACCOUNT_PASSWORD_ERROR);
        }

        return sysUserTokenService.createToken(userDTO.getId());
    }
}
