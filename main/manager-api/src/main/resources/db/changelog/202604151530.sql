-- 亲属信息表
CREATE TABLE IF NOT EXISTS ai_family_member
(
    id              BIGINT AUTO_INCREMENT COMMENT '主键ID' PRIMARY KEY,
    user_id         BIGINT NOT NULL COMMENT '所属用户ID',
    device_id       VARCHAR(32) COMMENT '设备ID',
    agent_id        VARCHAR(32) COMMENT '智能体ID',
    name            VARCHAR(50) NOT NULL COMMENT '亲属姓名',
    phone           VARCHAR(20) NOT NULL COMMENT '亲属手机号',
    remark          VARCHAR(200) COMMENT '备注',
    sort            INT DEFAULT 0 COMMENT '排序',
    status          TINYINT(1) DEFAULT 1 COMMENT '状态：0-禁用，1-启用',
    updater         BIGINT COMMENT '更新者',
    update_date     DATETIME COMMENT '更新时间',
    creator         BIGINT COMMENT '创建者',
    create_date     DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_ai_family_user_id (user_id),
    INDEX idx_ai_family_device_id (device_id),
    INDEX idx_ai_family_agent_id (agent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '亲属信息表';
