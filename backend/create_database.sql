-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS blue_local_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

-- 使用数据库
USE blue_local_db;

-- 显示创建结果
SELECT 'Database blue_local_db created successfully!' AS Message;
