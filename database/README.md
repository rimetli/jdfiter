# 数据库初始化

本项目使用 MySQL 8，数据库结构以 Alembic 迁移作为唯一事实来源；不要维护第二份手工建表 SQL，以免和代码不一致。

## 1. 创建数据库

执行 [init.sql](init.sql)：

```bash
mysql -h <MYSQL_HOST> -u <管理员账号> -p < database/init.sql
```

或在 MySQL 客户端中执行其中的 `CREATE DATABASE` 语句。

## 2. 配置应用

复制 `backend/.env.example` 为 `backend/.env`，填写：

```dotenv
MYSQL_HOST=你的数据库地址
MYSQL_PORT=3306
MYSQL_DATABASE=resume_screening
MYSQL_USERNAME=resume_app
MYSQL_PASSWORD=你的数据库密码
```

## 3. 创建全部表结构

```bash
cd backend
source .venv/bin/activate
python -m alembic upgrade head
```

该命令会依次创建组织、账户、岗位、能力模型、候选人、简历、任务、评估、证据与人工决策等全部表，并应用账户隔离、简历去重、评分深度等后续迁移。

## 4. 验证

```bash
python -m alembic current
```

输出应为最新修订：`a91d3e7f5b62` 或后续版本。

> 不提交 `backend/.env`、数据库密码或数据库备份。生产数据库迁移前请先备份。
