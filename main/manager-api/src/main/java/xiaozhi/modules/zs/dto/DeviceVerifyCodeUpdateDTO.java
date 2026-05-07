package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
@Schema(description = "修改设备验证码请求")
public class DeviceVerifyCodeUpdateDTO {

    @NotBlank(message = "MAC地址不能为空")
    @Schema(description = "设备 MAC 地址")
    private String macAddress;

    @NotBlank(message = "新验证码不能为空")
    @Schema(description = "新的设备验证码（同一用户下不可与其他设备重复）")
    private String newVerifyCode;
}
