# Ops Extension V1

独立运营扩展服务：工单、报账、费用报表。通过同域 `/ext/*` 嵌入 Sub2API，**不修改** Sub2API 源码。

## 能力概览

| 模块 | 说明 |
|------|------|
| Auth Bridge | Bootstrap 用 Sub2API `GET /api/v1/auth/me`（字段 `data.id`）签发 HttpOnly Session（`Path=/ext`） |
| 工单 | 用户建单（固定 P2）/回复/关单/附件；管理员认领·释放·接管·内部备注·改状态/分类/优先级 |
| 报账 | 仅 admin；供应商/成本中心/付款账户；公司直付 vs 个人垫付；允许申请人=审批人 |
| 报表 | 月/年、分类/供应商/成本中心、已付未付、有票无票税额；CSV/Excel |

## 路径约定

- `/ext/auth/*` — Bootstrap /（登出在 API）
- `/ext/api/*` — JSON API
- `/ext/app/*` — Vue SPA（`base: /ext/app/`）

## 技术栈

- Backend: FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL + MinIO
- Frontend: Vue3 + Vite + TypeScript + Tailwind + Pinia
- DB: `qiyuan_ops` · Bucket: `qiyuan-ops`

## 快速开始（Docker Compose）

```bash
# 若需与 Sub2API 同网互通 auth/me：
# docker network create qiyuan-network   # 或加入已有网络

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
export DATABASE_URL=postgresql+psycopg://ops:ops@localhost:5432/qiyuan_ops
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

建议 `hide_open_button=true`。iframe 会自动追加 `user_id`/`token`/`theme`/`lang`/`ui_mode`；Bootstrap 校验后 302 到干净 URL（无 token）。

## Auth Bridge 要点

1. 读取 query `token`（短暂）→ `Authorization: Bearer` 调 Sub2API `/api/v1/auth/me`
2. 要求 `status == active`；用户主键用响应 **`data.id`**（不是 `user_id`）
3. Upsert `extension_users`；写 `sessions`；Set-Cookie `ops_session` HttpOnly Secure SameSite=Lax Path=`/ext`
4. **禁止**把 token 写入业务库或明文日志；Nginx 示例已提示脱敏

V1 鉴权只看 `sub2api_role`（`user`|`admin`）；`extension_role` 列保留但未用于授权。报账/报表仅 admin。

## 环境变量

见 `.env.example`。切勿提交真实密钥。

## 验收相关行为（产品定稿）

- 用户创建工单优先级强制 P2；标题/描述创建后不可改
- CLOSED 终态不可重开；内部备注对用户 API 永不返回
- 认领使用原子 `UPDATE ... WHERE claimed_by_user_id IS NULL`；管理员可直接接管
- 附件 ≤20MB；白名单：图片 / PDF / `.log`/`.txt`
- 报账：`COMPANY_DIRECT` / `PERSONAL_ADVANCE`；结构化 `payment_accounts`；默认 CNY

## 目录

```
ops-extension/
├── backend/          # FastAPI 服务
├── frontend/         # Vue SPA
├── nginx/            # 主站 include 示例
├── scripts/          # seed + smoke
└── docker-compose.yml
```
