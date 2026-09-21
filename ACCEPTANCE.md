# Ops Extension V1 验收记录

环境：实施机无 Docker；已用 SQLite 内存库跑通后端单元/集成测试；前端 `npm run build` 成功。

## 已实现（对照实施方案 Phase1–4）

### Phase 1
- [x] Monorepo 骨架、docker-compose、`.env.example`、nginx 示例
- [x] SQLAlchemy models + Alembic `001_initial`（库名 `qiyuan_ops`，bucket `qiyuan-ops`）
- [x] Identity Adapter + Auth Bootstrap/Logout/Me + Session（Cookie Path=/ext）
- [x] `require_login` / `require_admin`（仅 `sub2api_role`）
- [x] MinIO 客户端 + 附件白名单/20MB
- [x] 种子：成本中心 + 示例付款账户

### Phase 2
- [x] 用户/管理工单 API（固定 P2、原子认领、释放、接管、内部备注、CLOSED 终态）
- [x] 用户/管理前端页
- [x] 测试：认领冲突、内部备注不可见、CLOSED 不可重开、创建强制 P2、admin 403

### Phase 3
- [x] 供应商/成本中心/付款账户 API + 主数据页
- [x] 报账 CRUD、明细、状态机、申请人=审批人、付款→PAID、发票、附件事件
- [x] pay_type COMPANY_DIRECT / PERSONAL_ADVANCE

### Phase 4
- [x] 汇总 / 分类 / 供应商 / 成本中心 / 付款状态 / 发票税额
- [x] CSV + Excel 导出
- [x] 报表前端页

## 测试结果（本机实测）

```text
cd backend && PYTHONPATH=. pytest -q
12 passed
```

```text
cd frontend && npm run build
✓ built successfully
```

Docker Compose / 真实 Postgres+MinIO+Sub2API 联调：本环境无 Docker，未在此机启动全栈；代码与 compose 已交付。

## 刻意偏差

1. **SQLite 测试**：PK 使用 `BigInteger.with_variant(Integer, "sqlite")`，仅影响测试方言；Postgres 仍为 BIGINT。
2. **DEV_AUTH_BYPASS**：可选开发捷径，默认关闭；生产必须走真实 `/auth/me`。
3. **主数据前端**：供应商/成本中心/付款账户合并为 `/admin/suppliers` 单页 Tab（路由仍保留 redirect）。
4. **Compose 网络**：`qiyuan-network` 默认由 compose 创建（非 external），便于独立拉起；与 Sub2API 共用时改为 external 即可。
