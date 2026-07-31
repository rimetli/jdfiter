# 02 技术架构与API

## 1. 架构原则

MVP采用“受控流水线＋确定性评分引擎”。LLM输出必须通过JSON Schema校验，失败时修复或重试；评分由后端规则计算。

```text
Vue 3 Web
  │
FastAPI ── MySQL 8
  ├─ 私有对象存储
  └─ MySQL任务表 ← Worker轮询/抢占
      ├─ PDF解析/OCR
      ├─ JD/简历结构化抽取
      ├─ 规则评分
      └─ 报告生成
```

### 1.1 推荐技术栈

- 前端：Vue 3、TypeScript、Vite、Vue Router、Pinia、Element Plus、ECharts、PDF.js
- 后端：Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、Alembic
- 数据库：MySQL 8.0
- 异步任务：MySQL `processing_tasks`任务表＋独立Python Worker
- 文件：S3兼容私有对象存储，开发环境可使用MinIO
- 文档：PyMuPDF；扫描件使用PaddleOCR
- AI：供应商SDK封装层＋JSON Schema结构化输出
- 部署：Nginx、Docker Compose；规模扩大后再迁移Kubernetes

LangGraph仅用于确实需要状态恢复、分支和人工介入的流程，不作为MVP必选依赖。

### 1.2 为什么优先Python

简历解析、OCR、模型SDK和AI评测主要位于Python生态。使用FastAPI可以让API服务和异步Worker复用同一套Pydantic Schema、Prompt和评分代码，避免Java调用独立Python AI服务产生重复模型和跨服务排错成本。

### 1.3 Java方案何时更合适

如果企业已有成熟的Java中台、统一Spring Security权限、运维规范和Java研发团队，可以采用：

```text
Vue 3 → Spring Boot 3 → MySQL 8
                   └→ Python AI Worker/API
```

Java负责用户、权限、岗位、候选人和业务API；Python负责PDF/OCR、LLM和评估任务。两者通过任务队列或内部HTTP通信。该方案治理能力更强，但MVP至少增加一个服务、两套部署和跨服务契约，暂不作为默认方案。

## 2. 处理流程

1. 上传文件并校验MIME、扩展名、大小、哈希和恶意文件。
2. PyMuPDF提取文本；文本不足时触发OCR。
3. 保存带页码、区块位置的规范化文本。
4. LLM按Schema抽取事实，不进行评价。
5. 匹配岗位能力项并附证据、状态和置信度。
6. 规则引擎计算明细及总分。
7. LLM基于已验证的事实和分数生成解释与面试问题。
8. 保存完整版本快照与调用日志。

## 3. API约定

- 前缀：`/api/v1`
- 鉴权：短时访问令牌＋刷新令牌或企业SSO
- 错误：统一`code/message/request_id/details`
- 列表：`page/page_size/sort/filter`
- 写操作支持`Idempotency-Key`
- 异步请求返回`202`及`task_id`

## 4. 核心API

### 岗位

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/jobs` | 创建岗位 |
| GET | `/jobs` | 岗位列表 |
| GET | `/jobs/{id}` | 岗位详情 |
| PATCH | `/jobs/{id}` | 修改草稿 |
| POST | `/jobs/{id}/analyze-jd` | 创建JD分析任务 |
| POST | `/jobs/{id}/requirement-versions` | 保存能力模型版本 |
| POST | `/jobs/{id}/requirement-versions/{vid}/publish` | 发布版本 |
| POST | `/jobs/{id}/archive` | 归档岗位 |

### 候选人与简历

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/jobs/{id}/resumes` | 上传一份或多份简历 |
| GET | `/jobs/{id}/candidates` | 候选人列表 |
| GET | `/candidates/{id}` | 候选人资料 |
| GET | `/resumes/{id}/download` | 鉴权后下载 |
| POST | `/resumes/{id}/reparse` | 创建新解析版本 |
| DELETE | `/candidates/{id}` | 发起合规删除 |

### 评估与反馈

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/evaluations/{id}` | 评估详情 |
| POST | `/evaluations/{id}/rerun` | 以指定规则版本重评 |
| POST | `/evaluations/{id}/human-decision` | 人工结论 |
| POST | `/evaluations/{id}/corrections` | 事实纠正 |
| POST | `/evaluations/{id}/interview-feedback` | 面试反馈 |
| POST | `/jobs/{id}/compare` | 横向比较2–5人 |

### 任务

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/tasks/{id}` | 查询任务 |
| GET | `/tasks` | 任务中心 |
| POST | `/tasks/{id}/retry` | 重试失败任务 |
| POST | `/tasks/{id}/cancel` | 取消可取消任务 |

## 5. 关键响应结构

```json
{
  "evaluation_id": "uuid",
  "status": "COMPLETED",
  "score": 78.5,
  "level": "RECOMMENDED",
  "gate_result": "REVIEW_REQUIRED",
  "dimensions": [
    {
      "code": "agent",
      "score": 23,
      "max_score": 30,
      "confidence": 0.86,
      "items": []
    }
  ],
  "advantages": [],
  "risks": [],
  "unknowns": [],
  "interview_questions": [],
  "versions": {
    "requirement": 3,
    "rubric": "1.0.0",
    "prompt": "resume-extract-1.0.0",
    "model": "provider/model"
  }
}
```

## 6. 稳定性与可观测性

- 超时、指数退避、最大3次自动重试。
- 每阶段可单独重跑，使用输入哈希避免重复计费。
- 记录request_id、task_id、阶段耗时、Token和费用，不记录完整简历正文。
- 指标：成功率、P95耗时、OCR触发率、Schema失败率、模型错误率、单份成本。
- 外部模型不可用时保留任务并允许稍后重试，不返回伪造结果。

## 7. 前后端工程结构

```text
apps/
  web/                 # Vue 3
  api/                 # FastAPI路由、鉴权、业务服务
  worker/              # MySQL任务轮询与处理入口
packages/
  domain/              # 领域模型和评分规则
  ai/                  # Prompt、Schema、模型适配器
  document/            # PDF与OCR
  shared/              # 配置、日志、错误码
```

前端只调用FastAPI，不直接访问模型、MySQL或对象存储。下载文件由后端鉴权后签发短时URL。
