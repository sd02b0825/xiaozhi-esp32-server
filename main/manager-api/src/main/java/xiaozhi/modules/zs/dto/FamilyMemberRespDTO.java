package xiaozhi.modules.zs.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@Schema(description = "亲属响应")
public class FamilyMemberRespDTO {

    @Schema(description = "ID")
    private Long id;

    @Schema(description = "设备ID")
    private String deviceId;

    @Schema(description = "智能体ID")
    private String agentId;

    @Schema(description = "亲属姓名")
    private String name;

    @Schema(description = "亲属手机号")
    private String phone;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "状态")
    private Integer status;

    @Schema(description = "创建时间")
    private String createDate;
}
