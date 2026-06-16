package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
@Schema(description = "修改设备智能体请求DTO")
public class DeviceUpdateAgentDTO {

    @NotBlank(message = "智能体名称不能为空")
    @Schema(description = "智能体名称")
    private String agentName;

    @Schema(description = "音色：male/female，暂不处理")
    private String voiceGender;

    @Schema(description = "语音风格：1/2/3，暂不处理")
    private Integer voiceStyle;
}
