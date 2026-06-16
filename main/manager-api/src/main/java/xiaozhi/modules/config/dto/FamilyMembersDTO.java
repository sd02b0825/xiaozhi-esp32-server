package xiaozhi.modules.config.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
@Schema(description = "获取设备亲属列表DTO")
public class FamilyMembersDTO {

    @NotBlank(message = "设备ID不能为空")
    @Schema(description = "设备ID")
    private String deviceId;
}
