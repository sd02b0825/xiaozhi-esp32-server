package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
@Schema(description = "亲属更新请求")
public class FamilyMemberUpdateDTO {

    @NotNull(message = "亲属ID不能为空")
    @Schema(description = "亲属ID")
    private Long id;

    @NotBlank(message = "设备验证码不能为空")
    @Schema(description = "设备验证码")
    private String verifyCode;

    @NotBlank(message = "亲属姓名不能为空")
    @Size(max = 50, message = "姓名长度不能超过50")
    @Schema(description = "亲属姓名")
    private String name;

    @NotBlank(message = "手机号不能为空")
    @Size(max = 20, message = "手机号长度不能超过20")
    @Schema(description = "亲属手机号")
    private String phone;

    @Size(max = 200, message = "备注长度不能超过200")
    @Schema(description = "备注")
    private String remark;
}
