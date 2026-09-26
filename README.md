# Ops Extension V1

独立运营扩展服务：工单、报账、费用报表。通过同域 `/ext/*` 嵌入 Sub2API，**不修改** Sub2API 源码。

## 能力概览

| 模块 | 说明 |
|------|------|
| Auth Bridge | Bootstrap 用 Sub2API `GET /api/v1/auth/me`（字段 `data.id`）签发 HttpOnly Session（`Path=/ext`） |
| 工单 | 用户建单（固定 P2）/回复/关单/附件；管理员认领·释放·接管·内部备注·改状态/分类/优先级 |
| 报账 | 仅 admin；供应商/成本中心/付款账户；公司直付 vs 个人垫付；允许申请人=审批人；分次付款、完整发票信息和附件 |
| 报表 | 按币种分别展示月/年、分类/供应商/成本中心、付款和发票统计；明细与汇总 CSV/Excel |

## 路径约定

- `/ext/auth/*` — Bootstrap /（登出在 API）
- `/ext/api/*` — JSON API
- `/ext/app/*` — Vue SPA（`base: /ext/app/`）

## 技术栈

- Backend: FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL + MinIO
- Frontend: Vue3 + Vite + TypeScript + Tailwind + Pinia
- DB: `huima_ops` · Bucket: `huima-ops`

## 快速开始（Docker Compose）

Compose 使用 [MinIO 官方容器文档](https://min.io/docs/minio/container/index.html)中的 Quay 镜像地址；部署前确认可访问该镜像仓库。

```bash
# 若需与 Sub2API 同网互通 auth/me：
# docker network create huima-network   # 或加入已有网络

cp .env.example .env   # 修改密钥
docker compose up -d --build
# Backend :8090  Frontend :8088
# 主站 Nginx 请 include nginx/ext.conf.example
```

启动后 backend 容器会执行 `alembic upgrade head` 与种子脚本。

## 本地开发

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://ops:ops@localhost:5432/huima_ops
export DEV_AUTH_BYPASS=true   # 本地可跳过真实 Sub2API；bootstrap token 用 JSON
alembic upgrade head
python -m scripts.seed_defaults
uvicorn app.main:app --reload --port 8090
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173/ext/app/  已代理 /ext/api 与 /ext/auth
```

### 测试

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. pytest -q
```

### Smoke

```bash
DEV_AUTH_BYPASS=true ./scripts/smoke_test.sh
```

## Sub2API Custom Menu 配置

在 Sub2API 管理后台 → Custom Menu Items，配置**绝对 URL**（同域）：

| 菜单 | visibility | url |
|------|------------|-----|
| 我的工单 | user | `https://<domain>/ext/auth/bootstrap?next=/ext/app/tickets` |
| 工单管理 | admin | `https://<domain>/ext/auth/bootstrap?next=/ext/app/admin/tickets` |
| 报账管理 | admin | `https://<domain>/ext/auth/bootstrap?next=/ext/app/admin/expenses` |
| 费用报表 | admin | `https://<domain>/ext/auth/bootstrap?next=/ext/app/admin/reports` |

建议 `hide_open_button=true`。iframe 会自动追加 `user_id`/`token`/`theme`/`lang`/`ui_mode`；Bootstrap 校验后 302 到干净 URL（无 token）。**菜单必须指向 bootstrap**（不要直链 `/ext/app/...`），以便无入库 token 时仍能刷新身份快照与 Session。

### 前端视觉适配

扩展前端按 Sub2API 官方主线的浅色、深色设计体系维护独立样式，不引用宿主 CSS。Bootstrap 保存的 `ops_theme` Cookie 会在页面渲染前应用；没有主题参数时默认浅色。iframe 中隐藏扩展自身导航，由 Sub2API 侧边栏的四个自定义菜单切换模块；独立打开扩展时仍显示自身导航。“主数据”从“报账管理”页面进入。视觉基准参考 [Sub2API 的样式定义](https://github.com/Wei-Shaw/sub2api/blob/a3eb7ef302961cba716dc78b39b93b60c467db0e/frontend/src/style.css)，宿主升级后可据此核对控件与主题差异。

## Auth Bridge 要点

1. 读取 query `token`（短暂）→ `Authorization: Bearer` 调 Sub2API `/api/v1/auth/me`
2. 要求 `status == active`；用户主键用响应 **`data.id`**（不是 `user_id`）
3. Upsert `extension_users`（刷新 username/email/role **快照**）；写 `sessions`（仅 id / user_id / expires / `last_checked_at`）；Set-Cookie `ops_session` HttpOnly Secure SameSite=Lax Path=`/ext`
4. **Token 禁止写入业务库**（含密文/密封）、禁止写 Redis/文件，也禁止写入日志明文。Bearer 仅在 Bootstrap 请求生命周期内使用，用完即弃。Nginx `access_log ... ops_ext` 脱敏 query token
5. **Session 新鲜度（无存 token 重验）**：Custom Menu **必须**指向 `/ext/auth/bootstrap`。Bootstrap 刷新快照并重置 `last_checked_at`。两次 Bootstrap 之间信任快照，直到 `SESSION_TTL_HOURS` 到期，或距上次 Bootstrap 超过 `SESSION_MAX_AGE_WITHOUT_BOOTSTRAP`（默认 2h）→ 清 Session 并 **401 `SESSION_REBOOTSTRAP_REQUIRED`**，前端/宿主引导用户重新打开菜单走 Bootstrap。**不会**用入库 bearer 回调 Sub2API `/auth/me`

V1 鉴权只看 `sub2api_role`（`user`|`admin`）；`extension_role` 列保留但未用于授权。报账/报表仅 admin。

## 环境变量

见 `.env.example`。切勿提交真实密钥。关键项：

| 变量 | 说明 |
|------|------|
| `SESSION_TTL_HOURS` | Session / Cookie 绝对 TTL，默认 `2` |
| `SESSION_MAX_AGE_WITHOUT_BOOTSTRAP` | 距上次 Bootstrap 的最大秒数，超时 401 强制重登，默认 `7200` |
| `MINIO_ENDPOINT` | 后端访问 MinIO（可为 compose 内网 `minio:9000`） |
| `MINIO_PUBLIC_ENDPOINT` / `MINIO_PUBLIC_URL` | 可选；配置后下载可 302 Presigned；**未配置则始终 API 流式代理** |

## 验收相关行为（产品定稿）

- 用户创建工单优先级强制 P2；标题/描述创建后不可改
- CLOSED 终态不可重开；内部备注对用户 API 永不返回
- 认领使用原子 `UPDATE ... WHERE claimed_by_user_id IS NULL`；管理员可直接接管
- 附件 ≤20MB；白名单：图片 / PDF / `.log`/`.txt`
- 附件下载默认经 **后端鉴权流式代理**（不依赖浏览器直连 compose 内 `minio:9000`）。仅当配置 `MINIO_PUBLIC_ENDPOINT` 或 `MINIO_PUBLIC_URL` 时才 302 到公网 Presigned URL
- 工单号按日序列分配（PG advisory lock + unique 冲突重试），避免并发撞号 500
- 报账：`COMPANY_DIRECT` / `PERSONAL_ADVANCE`；结构化 `payment_accounts`；默认 CNY

## 报账付款与报表口径

- 付款仅对 `APPROVED` 单开放；金额须大于零、精确到分，币种与单据相同且不得超过未付余额。允许分次付款，累计恰好付清时自动转为 `PAID`；`PAID` 不再接收付款。
- `POST /ext/api/v1/admin/expenses/{id}/payments` 示例：`{"amount":"30.00","reference_no":"bank-ref"}`。省略 `currency` 时继承单据币种。旧请求的 `mark_paid=true` 不能使不足额付款变为已付，不足额时返回 `PAYMENT_INCOMPLETE`。
- `GET /ext/api/v1/admin/expenses/{id}` 增加 `payments`、`attachments`、`paid_total`、`remaining_amount`、`payment_reconciliation_required`；报账列表响应保持原结构。附件下载示例：`/ext/api/v1/attachments/{id}/download?source=expense`（仅管理员）。
- 费用支出只计 `APPROVED` 和 `PAID`；`SUBMITTED`、`REJECTED` 分别列示。已付取实际付款流水，未付取审批单剩余金额。均按费用日期归期，按币种分别汇总，不进行汇率换算或跨币种相加。历史异常付款不计入付款统计，并在页面显示待核对单号。
- **报表 API 响应结构已调整**：`GET /ext/api/v1/admin/reports/summary?period=year&year=2026` 返回 `{"period":"year","year":2026,"currencies":[{"currency":"CNY","count":1,"total_amount":100.0,"tax_amount":6.0,"by_status":{"APPROVED":{"count":1,"amount":100.0}}}]}`（另含 `month/start/end`）；付款、发票接口也使用 `currencies` 数组。分类、供应商、成本中心及新增 `by-month` 返回每行含 `currency` 的数组。以上接口支持可选 `currency` 筛选，前后端须配套部署。
- `GET /ext/api/v1/admin/reports/export` 支持 `format=csv|xlsx` 与 `view=detail|summary|month|category|supplier|cost_center|payment|invoice|all`。CSV 每次选一种视图；Excel 使用 `view=all` 可一次导出全部工作表。省略 `view` 继续导出明细；空结果保留表头。明细导出含 `payment_reconciliation_required`，历史付款异常须先核对。

## 历史付款核对与发布

1. 发布前备份 Ops 数据库，并在独立环境安装后端锁定依赖、执行迁移及测试。此版本不新增数据库列，也不自动修复历史数据。
2. 从 `backend` 目录运行 `python -m scripts.reconcile_payments audit > payment-audit.csv`。该命令只读，列出已付未足额、超付、付款币种不符的单据。业务人员逐单核对其他付款凭证；有异常且未核清时，付款报表不能作为财务验收结果。
3. 对确认无其他付款的 `PAID` 单，用 `restore_approved` 恢复为 `APPROVED`；对有外部付款凭证的，用 `record_payment` 补录。仅允许处理核对清单中指定的单号，并校验 `expected_amount`、`expected_paid`。清单列为 `claim_no,expected_amount,expected_paid,action,reason,reference_no,payment_date`；补录必须提供交易号及带时区的 ISO 付款时间。超付和币种不符须另行调查，不通过此工具猜测修正。
4. 核对后运行 `python -m scripts.reconcile_payments apply --approved-list reviewed.csv --actor-user-id <extension_admin_id>`。整份清单在一次事务内执行；任何金额变化或校验失败都回滚，成功写入 `PAYMENT_RECONCILED` 事件。再次运行 `audit` 并复核报表。上线时同步发布后端与前端；如需回滚代码，先保留数据库备份和修正清单，历史修正只能依据事件和凭证逐单反向处理。

## 目录

```
ops-extension/
├── backend/          # FastAPI 服务
├── frontend/         # Vue SPA
├── nginx/            # 主站 include 示例
├── scripts/          # seed + smoke
└── docker-compose.yml
```
