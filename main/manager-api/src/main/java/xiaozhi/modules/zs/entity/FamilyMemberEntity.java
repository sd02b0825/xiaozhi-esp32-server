package xiaozhi.modules.zs.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = false)
@TableName("ai_family_member")
@Schema(description = "亲属信息")
public class FamilyMemberEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "ID")
    private Integer id;

    @Schema(description = "所属用户ID")
    private Long userId;

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

    @Schema(description = "排序")
    private Integer sort;

    @Schema(description = "状态：0-禁用，1-启用")
    private Integer status;

    @TableField(fill = FieldFill.UPDATE)
    @Schema(description = "更新者")
    private Long updater;

    @TableField(fill = FieldFill.UPDATE)
    @Schema(description = "更新时间")
    private Date updateDate;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建者")
    private Long creator;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private Date createDate;
}
