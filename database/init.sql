-- AI 招聘简历筛选系统：MySQL 数据库初始化
-- 表结构由 backend/migrations/versions/ 中的 Alembic 迁移维护。
-- 创建数据库后，请执行：cd backend && python -m alembic upgrade head

CREATE DATABASE IF NOT EXISTS `resume_screening`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- 可选：为应用创建最小权限账号。请替换账号、密码和允许连接的主机。
-- CREATE USER 'resume_app'@'%' IDENTIFIED BY 'replace-with-a-strong-password';
-- GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX,
--       REFERENCES ON `resume_screening`.* TO 'resume_app'@'%';
-- FLUSH PRIVILEGES;
