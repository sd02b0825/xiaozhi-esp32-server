package xiaozhi.modules.zs.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@Schema(description = "批量录入设备响应DTO")
public class DeviceBatchAddRespDTO {

    @Schema(description = "成功数量")
    private Integer successCount;

    @Schema(description = "失败数量")
    private Integer failCount;

    @Schema(description = "失败详情列表")
    private List<FailItemDTO> failList;

    @Data
    @Schema(description = "失败项")
    public static class FailItemDTO {

        @Schema(description = "MAC地址")
        private String macAddress;

        @Schema(description = "失败原因")
        private String reason;

        public FailItemDTO() {
        }

        public FailItemDTO(String macAddress, String reason) {
            this.macAddress = macAddress;
            this.reason = reason;
        }
    }
}
