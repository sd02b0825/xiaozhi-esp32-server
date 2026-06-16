package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 声纹录音更新请求DTO
 */
@Data
@Schema(description = "声纹录音更新请求")
public class VoicePrintUpdateDTO {

    @NotBlank(message = "设备验证码不能为空")
    @Schema(description = "设备验证码")
    private String verifyCode;

    @NotBlank(message = "声纹ID不能为空")
    @Schema(description = "声纹ID")
    private String id;

    @Schema(description = "音频文件ID")
    private String audioId;

    @Size(max = 50, message = "称呼长度不能超过50")
    @Schema(description = "声纹来源的人称呼/姓名")
    private String sourceName;

    @Size(max = 200, message = "描述长度不能超过200")
    @Schema(description = "描述声纹来源的人")
    private String introduce;
}
