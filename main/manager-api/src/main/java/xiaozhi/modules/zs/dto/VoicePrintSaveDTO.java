package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 声纹录音保存请求DTO
 */
@Data
@Schema(description = "声纹录音保存请求")
public class VoicePrintSaveDTO {

    @NotBlank(message = "设备验证码不能为空")
    @Schema(description = "设备验证码")
    private String verifyCode;

    @Schema(description = "音频文件ID")
    private String audioId;

    @Schema(description = "base64编码的opus音频数据（与audioId二选一）")
    private String audioBase64;

    @NotBlank(message = "称呼不能为空")
    @Size(max = 50, message = "称呼长度不能超过50")
    @Schema(description = "声纹来源的人称呼/姓名")
    private String sourceName;

    @Size(max = 200, message = "描述长度不能超过200")
    @Schema(description = "描述声纹来源的人")
    private String introduce;

    @Schema(description = "MAC地址（用于关联聊天记录）")
    private String macAddress;
}
