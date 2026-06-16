package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Data
@Schema(description = "亲属批量保存请求")
public class FamilyMemberBatchSaveDTO {

    @NotBlank(message = "设备验证码不能为空")
    @Schema(description = "设备验证码")
    private String verifyCode;

    @Valid
    @NotEmpty(message = "亲属列表不能为空")
    @Schema(description = "亲属列表")
    private List<MemberItem> members;

    @Data
    @Schema(description = "亲属信息")
    public static class MemberItem {
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
}
