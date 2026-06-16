package xiaozhi.modules.zs.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotEmpty;
import lombok.Data;

@Data
@Schema(description = "批量删除设备绑定智能体请求")
public class DeviceBindAgentBatchDeleteDTO {

    @NotEmpty(message = "智能体ID列表不能为空")
    @Schema(description = "智能体ID列表（与单条删除规则一致：须为当前用户下已绑定设备的智能体）")
    private List<String> agentIds;
}
