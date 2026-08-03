# 02 技术架构与 API

> 文档基线：当前代码实现，而非目标架构。

## 1. 架构

```text
Vue 3 + Vite（5173）
        │ HTTP / Bearer Token
FastAPI（8000） ───────── MySQL 8
  │  本地文件存储                │
  └───────────────── processing_tasks
                                  │ 轮询、抢占
                            Python Worker
                    ┌─────────────┴──────────────┐
                    PDF 文本提取 / 视觉模型 OCR / LLM 评估
```

| 层 | 当前技术与职责 |
|---|---|
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Element Plus；调用 REST API，不直接访问数据库或模型 |
| API | FastAPI、Pydantic、SQLAlchemy Async；处理认证、岗位、上传、任务查询和结果展示 |
| 数据库 | MySQL 8 + asyncmy；Alembic 管理结构迁移 |
| 异步处理 | `processing_tasks` 表 + 独立 Python Worker，无 Redis |
| 文件 | 本地 `LOCAL_STORAGE_PATH`；数据库保存相对存储键 |
| PDF/OCR | PyPDF 文本提取；PyMuPDF 转图片后调用兼容 OpenAI Chat Completions 的视觉模型 |
| LLM | 兼容 OpenAI `chat/completions` 的 JD 分析、简历画像和人岗匹配调用 |

## 2. 简历处理过程

1. API 校验扩展名、PDF 文件头和 20 MB 大小限制。
2. 使用 PyPDF 提取文本；少于 30 字时调用视觉模型 OCR（默认最多 5 页、160 DPI）。
3. 从文本中识别姓名、电话、邮箱，按“电话优先；无电话时邮箱”去重。
4. 将文件及预解析文字保存到本地存储，创建 `PARSE_RESUME` 任务。
5. Worker 读取任务，生成结构化画像与 `resume_parse_versions`。
6. 用户选中已解析的申请记录，批量创建 `ANALYZE_APPLICATION` 任务。
7. Worker 读取已发布能力模型，调用模型匹配并用代码计算分数、写入证据和评估结果。

## 3. 认证与访问控制现状

- 首次初始化由 `/api/v1/setup/bootstrap` 创建组织；`/api/v1/setup/admin` 仅在系统没有用户时可创建首位管理员。
- `POST /api/v1/auth/login` 使用邮箱和密码登录，返回 HMAC 签名的 Bearer Token；有效期为 24 小时。
- 密码使用 `hashlib.scrypt` 派生哈希保存，数据库不保存明文密码。
- 管理员可通过 `/api/v1/auth/users` 创建普通用户。
- 所有候选人、简历上传、批量分析、能力模型、评估和任务接口均要求 Bearer Token。普通用户通过“资源 → 申请/岗位”链路只能访问自己创建的岗位数据；管理员可访问同组织全部数据。
- 简历身份声明按“组织 + 账户 + 电话/邮箱”唯一，普通用户之间不会复用候选人和简历。历史数据未绑定账户时，仅管理员可安全处理。
- 初始化状态接口可匿名访问，以支持首次安装；组织枚举接口已移除。首次初始化接口仅应在受控网络环境中开放。

## 4. 实际路由

所有业务路由前缀为 `/api/v1`。下表列出当前实现的主要接口，不表示尚未实现的规划接口。

| 分组 | 方法和路径 | 说明 |
|---|---|---|
| 健康检查 | `GET /health`、`GET /health/database` | 服务与数据库连通性 |
| 初始化 | `GET /setup/status`、`POST /setup/bootstrap`、`POST /setup/admin` | 首次组织/管理员初始化 |
| 认证 | `POST /auth/login`、`GET /auth/me` | 登录和当前账户 |
| 账户 | `GET /auth/users`、`POST /auth/users` | 仅管理员列出/创建普通账户 |
| 岗位 | `POST/GET /jobs`、`GET/PATCH/DELETE /jobs/{id}` | 岗位管理；删除为物理清理逻辑 |
| JD | `POST /jobs/{id}/analyze-jd` | 分析 JD 并保存能力模型草稿 |
| 能力模型 | `GET /jobs/{id}/requirement-versions`、`GET/PATCH /jobs/{id}/requirement-versions/{vid}`、`POST .../publish` | 查看、修改、发布能力模型 |
| 简历 | `POST /jobs/{id}/resumes` | 单文件上传；前端可并发批量调用 |
| 候选人 | `GET /jobs/{id}/candidates`、`POST /jobs/{id}/evaluations/batch` | 列表与批量分析 |
| 任务 | `GET /tasks/{id}`、`POST /tasks/{id}/retry` | 查询、重试失败任务 |
| 评估 | `GET /evaluations/{id}`、`POST /evaluations/{id}/human-decision` | 查看结果和记录人工决定 |

## 5. 配置

`backend/.env` 是本地私密配置，不提交版本库。核心配置如下：

| 配置 | 用途 |
|---|---|
| `MYSQL_*` | MySQL 地址、端口、库名、账号与密码 |
| `LLM_PROVIDER/BASE_URL/API_KEY/MODEL` | JD 和简历分析模型 |
| `RESUME_LLM_ENABLED` | 是否由模型生成简历画像与评估 |
| `RESUME_VISION_ENABLED/MODEL/MAX_PAGES/DPI` | 扫描件视觉 OCR |
| `TASK_MAX_ATTEMPTS/LEASE_SECONDS/HEARTBEAT_SECONDS` | Worker 最大自动尝试次数、任务租约和心跳周期 |
| `TASK_RETRY_BASE_SECONDS/RETRY_MAX_SECONDS` | Worker 指数退避的初始与最大等待时间 |
| `LOCAL_STORAGE_PATH` | PDF 和预解析文字本地存储目录 |
| `APP_SECRET` | Bearer Token 签名密钥；生产环境必须随机且保密 |

## 6. 运行与故障定位

- API 仅负责创建/查询任务；“一直等待解析”通常表示 Worker 未启动、数据库连接异常或模型/OCR 调用失败。
- Worker 每 30 秒回收过期租约；失败任务按指数退避自动重试，达到最大尝试次数后标记为 `FAILED`，可由有权限的用户手动重试。
- 先查 `GET /api/v1/tasks/{id}` 的 `status`、`error_code`、`error_message`，再查看 Worker 日志。
- JD 分析失败通常与 `LLM_*` 配置、模型接口兼容性或模型返回的结构不符有关。
- 扫描件失败通常与视觉模型不支持图片输入、密钥/地址错误、页数限制或 PDF 图像质量有关。
