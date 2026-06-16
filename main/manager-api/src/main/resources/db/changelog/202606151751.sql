-- 新增灵芯配置参数
SET @col_exists = (SELECT COUNT(*) FROM sys_params where param_code='lingxin_json');
SET @sql = IF(@col_exists = 0, 'INSERT INTO `sys_params` (id,param_code, param_value, value_type, param_type, remark) VALUES (1001,''lingxin_json'', ''null'', ''string'', 1, ''灵芯配置'')', 'SELECT ''lingxin_json already exists'' AS msg');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;