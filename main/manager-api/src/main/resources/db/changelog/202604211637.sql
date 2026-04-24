-- 智能体表添加唤醒词字段
ALTER TABLE ai_agent ADD COLUMN wake_word VARCHAR(255) DEFAULT NULL COMMENT '唤醒词';

