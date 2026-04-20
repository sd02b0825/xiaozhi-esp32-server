-- 添加设备验证码字段
ALTER TABLE `ai_device` ADD COLUMN `verify_code` VARCHAR(50) DEFAULT NULL COMMENT '验证码' AFTER `mac_address`;
