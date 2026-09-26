# Ops Extension 新加坡 VPS 部署手册

本手册适用于已安装 Docker 和 Docker Compose 插件的 Linux VPS。Ops Extension 与 Sub2API 分别部署、分别更新；此仓库当前的交付单元是**独立 Docker Compose 服务栈**，不是单个容器：`ops-frontend`（Nginx 静态页面）、`ops-backend`（FastAPI）、`ops-db`（PostgreSQL）、`minio`（附件存储），以及运行完即退出的 `createbuckets` 初始化容器。Sub2API 不使用 Ops 的数据库或对象存储。

本手册只部署 Ops 服务。将它接入现有 Sub2API 域名和自定义菜单，请接着阅读 [Sub2API 对接手册](./Sub2API对接手册.md)。下文以已有 HTTPS 域名 `https://sub2api.example.com`、宿主机 Nginx 为例；域名、容器名和端口均须按实际环境替换。没有执行远程 VPS 部署。

## 1. 部署前确认

在 VPS 上检查：

```bash
docker --version
docker compose version
docker ps
ss -ltn
df -h
```

确认 VPS 可以拉取 `postgres:16-alpine`、`quay.io/minio/minio:latest`、`quay.io/minio/mc:latest`、`node:20-alpine` 和 `python:3.12-slim`。如果访问 Docker Hub 或 Quay 缓慢，先配置可信的镜像加速或镜像仓库，再执行构建。检查 `8088`、`8090` 是否被占用；它们仅是本机反代入口，可按需修改。公网只需沿用 Sub2API 的 HTTPS 入口，不需要为 Ops 再开放一组公网端口。

先确认要部署的代码版本。服务器执行 `git clone` 或 `git pull` 只能得到已经推送到远端的代码；应先确认所需的前端视觉改动已经发布，再在 VPS 获取对应提交或发布包，并记录提交号：

```bash
git clone <Ops-Extension-仓库地址> /opt/ops-extension
cd /opt/ops-extension
git rev-parse --short HEAD
```

后续命令均在 `/opt/ops-extension` 执行。不要把本地截图时使用的开发鉴权、示例数据库或临时容器当作生产环境。

## 2. 配置 Compose 与密钥

先阅读 [docker-compose.yml](../docker-compose.yml) 和 [.env.example](../.env.example)。**当前 Compose 文件直接写了示例密码和地址，没有 `${变量}` 插值；仅复制、修改 `.env` 不会改变容器配置。** Docker Compose 只有在 Compose 值实际引用 `${VAR}` 时才会读取 `.env` 用于替换，见 [Docker 官方说明](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)。

正式启动前，把 `docker-compose.yml` 中下表的字段改为 `${VAR:?required}` 插值并发布这个配置改动；VPS 上只在未提交的 `.env` 中填写真实值。也可以在 VPS 上临时直接替换示例值，但那会修改 Git 跟踪的 Compose 文件，后续更新时需要人工核对并保留这些改动。不要把真实密钥提交到 Git：

| 配置位置 | 要设置的内容 |
| --- | --- |
| `ops-db.POSTGRES_PASSWORD` 与 `ops-backend.DATABASE_URL` | 同一个独立数据库密码；`DATABASE_URL` 的主机保留 `ops-db:5432`，数据库保留 `huima_ops`。若密码含 URL 特殊字符，需要做 URL 编码；使用随机十六进制密码可简化配置。 |
| `minio.MINIO_ROOT_USER/PASSWORD`、`createbuckets` 的 `mc alias set`、`ops-backend.MINIO_ACCESS_KEY/SECRET_KEY` | 三处使用同一组新凭据；存储地址保留 `minio:9000`，Bucket 保留 `huima-ops`。 |
| `ops-backend.SUB2API_BASE_URL` | 后端容器可以访问的 Sub2API 地址。优先填现有 `https://sub2api.example.com` 并验证容器内连通；若 VPS 不允许经公网域名回连，则按对接手册使用共享 Docker 网络和真实服务名。不能填容器内的 `localhost`。 |
| `ops-backend.PUBLIC_BASE_URL` | `https://sub2api.example.com`，不带末尾 `/`。 |
| `ops-backend.SESSION_SECRET` | 独立随机长值，例如由 `openssl rand -hex 32` 生成。 |
| `ops-backend.COOKIE_SECURE`、`DEV_AUTH_BYPASS` | HTTPS 下保持 `COOKIE_SECURE=true`；明确设置 `DEV_AUTH_BYPASS=false`。 |

宿主机 Nginx 反代时，把 `ops-frontend` 的端口映射从 `8088:80` 改为 `127.0.0.1:8088:80`，把 `ops-backend` 的 `8090:8090` 改为 `127.0.0.1:8090:8090`。MinIO 只供 Compose 内部使用，删除其 `9000:9000`、`9001:9001` 公网端口映射；确需使用控制台时再单独配置受限访问。若主站 Nginx 本身也是容器，应改用共享 Docker 网络和服务名代理，不要在 Nginx 容器中使用 `127.0.0.1` 指向 Ops。

如果选择 `.env` 插值，示意写法如下；数据库、MinIO 初始化和后端中的对应值都要同步改，不能只改一处：

```yaml
services:
  ops-db:
    environment:
      POSTGRES_PASSWORD: ${OPS_DB_PASSWORD:?set OPS_DB_PASSWORD}
  ops-backend:
    environment:
      SUB2API_BASE_URL: ${SUB2API_BASE_URL:?set SUB2API_BASE_URL}
      PUBLIC_BASE_URL: ${PUBLIC_BASE_URL:?set PUBLIC_BASE_URL}
      SESSION_SECRET: ${SESSION_SECRET:?set SESSION_SECRET}
      COOKIE_SECURE: "true"
      DEV_AUTH_BYPASS: "false"
```

配置完成后用 `docker compose config --quiet` 检查解析是否成功。不要把不带 `--quiet` 的完整配置输出贴到工单或聊天里，因为它会展开密码。

## 3. 构建并启动

```bash
cd /opt/ops-extension
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=80 ops-backend ops-frontend ops-db minio createbuckets
```

后端容器启动命令会执行 `alembic upgrade head` 和 `python -m scripts.seed_defaults`。`createbuckets` 是一次性任务，正常运行完后显示 `Exited (0)`；前端、后端、数据库和 MinIO 应保持运行。初次构建会下载依赖与镜像。

`seed_defaults` 会添加**示例付款账户**。正式办理报账前，在页面“报账管理 → 主数据 → 付款账户”中核对并禁用或替换示例账户，不要将示例值用于实际付款。

从 VPS 本机验证：

```bash
curl -fsS http://127.0.0.1:8090/ext/api/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/ext/app/
```

预期健康接口返回 `{"ok":true,"service":"ops-extension"}`，前端返回 `200`。健康接口只验证进程响应；数据库迁移、身份桥接和附件功能仍需在对接后分别验收。检查容器内能否到达 Sub2API：

```bash
docker compose exec ops-backend python -c 'import os,httpx; u=os.environ["SUB2API_BASE_URL"].rstrip("/")+"/api/v1/auth/me"; r=httpx.get(u,timeout=10); print(r.status_code)'
```

不带身份令牌返回 `401` 属于可达的正常结果；DNS、TLS 或连接错误表示地址需要调整。不要把真实登录 token 放进命令行、日志或测试文档。

## 4. 日常操作、备份和更新

```bash
cd /opt/ops-extension
docker compose ps
docker compose logs --tail=100 ops-backend
mkdir -p backups
docker compose exec -T ops-db pg_dump -U ops -d huima_ops -Fc > "backups/huima_ops-$(date +%F).dump"
```

数据库之外，还需备份 `ops-minio` 数据卷中的附件；可使用 VPS 磁盘快照或经验证的对象存储备份流程。定期做恢复演练。更新前备份数据库和附件，阅读目标版本的迁移说明。如果 VPS 上没有直接修改 Git 跟踪的配置文件，再在已发布新代码的目录中执行：

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8090/ext/api/health
```

前后端需同版本发布。如果曾直接修改 VPS 上 Git 跟踪的 `docker-compose.yml`，先检查 `git status`，保留生产配置并人工合并更新；不能盲目执行 `git pull --ff-only`。`docker compose down` 不会主动删除命名数据卷；**不要执行 `docker compose down -v`**，它会删除 Ops 数据库和附件卷。若业务中已有付款数据，更新前还应按 [README 的付款核对流程](../README.md#历史付款核对与发布)执行只读审计，并保留核对结果。

## 5. 排查入口

| 现象 | 先检查 |
| --- | --- |
| `ops-backend` 启动失败 | `docker compose logs ops-backend ops-db`；数据库密码、迁移结果和数据库健康状态。 |
| 附件上传失败 | `docker compose logs minio createbuckets ops-backend`；三处 MinIO 凭据及 Bucket。后端首次上传也会尝试创建 Bucket。 |
| 容器内无法连接 Sub2API | `SUB2API_BASE_URL`、VPS 的 DNS/出站网络、共享 Docker 网络；容器内 `localhost` 不是宿主机。 |
| 服务器已有端口占用 | 修改本机端口映射，并同步修改对接手册中的反向代理目标。 |

完成本手册后，继续配置同域反向代理和 Sub2API 菜单；仅启动这些容器还不会在 Sub2API 中出现入口。
