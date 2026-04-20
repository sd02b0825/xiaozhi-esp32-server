package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@Schema(description = "设备绑定智能体响应DTO")
public class DeviceBindAgentRespDTO {

    @Schema(description = "智能体ID")
    private String agentId;

    @Schema(description = "智能体名称")
    private String agentName;

    @Schema(description = "设备ID")
    private String deviceId;

    @Schema(description = "MAC地址")
    private String macAddress;
}
