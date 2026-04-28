package xiaozhi.modules.zs.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
@Schema(description = "批量录入设备请求DTO")
public class DeviceBatchAddDTO {

    @NotEmpty(message = "设备列表不能为空")
    @Size(max = 100, message = "单次批量录入设备数量不能超过100个")
    @Valid
    @Schema(description = "设备列表")
    private List<DeviceItemDTO> devices;

    @Data
    @Schema(description = "设备项")
    public static class DeviceItemDTO {

        @NotEmpty(message = "MAC地址不能为空")
        @Pattern(regexp = "^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", message = "MAC地址格式不正确")
        @Schema(description = "MAC地址")
        private String macAddress;

        @NotEmpty(message = "验证码不能为空")
        @Schema(description = "验证码")
        private String verifyCode;
    }
}
