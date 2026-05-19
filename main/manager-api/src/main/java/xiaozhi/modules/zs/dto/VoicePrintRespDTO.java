package xiaozhi.modules.zs.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 声纹录音响应DTO
 */
@Data
@Schema(description = "声纹录音响应")
public class VoicePrintRespDTO {

    @Schema(description = "声纹ID列表")
    private List<String> idList;

    @Schema(description = "音频文件ID")
    private String audioId;

    @Schema(description = "声纹来源的人称呼/姓名")
    private String sourceName;

    @Schema(description = "描述声纹来源的人")
    private String introduce;

    @Schema(description = "创建时间")
    private String createDate;
}
