-- 新增说话人字段
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_agent_chat_history' AND COLUMN_NAME = 'speaker');
SET @sql = IF(@col_exists = 0, 'ALTER TABLE `ai_agent_chat_history` ADD COLUMN `speaker` varchar(100) DEFAULT NULL COMMENT ''说话人''', 'SELECT ''Column speaker already exists'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;



-- 新增环境声音检测url参数
SET @col_exists = (SELECT COUNT(*) FROM sys_params where param_code='audio_monitor_url');
SET @sql = IF(@col_exists = 0, 'INSERT INTO `sys_params` (id,param_code, param_value, value_type, param_type, remark) VALUES (1000,''audio_monitor_url'', ''null'', ''string'', 1, ''环境声音检测接口地址'')', 'SELECT ''audio_monitor_url already exists'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
