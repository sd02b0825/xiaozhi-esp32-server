ALTER TABLE `xiaozhi_esp32_server`.`ai_agent_chat_history` 
ADD COLUMN `speaker` varchar(100) NULL COMMENT '说话人' AFTER `updated_at`;

INSERT INTO `sys_params` (param_code, param_value, value_type, param_type, remark) VALUES ('audio_monitor_url', 'null', 'string', 1, '环境声音检测接口地址');
