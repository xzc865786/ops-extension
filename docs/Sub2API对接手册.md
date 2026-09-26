# Ops Extension 与现有 Sub2API 对接手册

本手册适用于 Sub2API 已在 Linux VPS 上运行，Ops Extension 已按 [新加坡 VPS 部署手册](./新加坡VPS部署手册.md)启动的场景。目标是让 Ops 保持独立服务，通过 Sub2API **现有 HTTPS 域名**下的 `/ext/*` 路径访问，再由 Sub2API 自定义菜单嵌入 iframe。无需修改 Sub2API 源码、数据库表或前端构建产物。下文以 `https://sub2api.example.com` 为占位域名。

## 1. 先确认连接关系

```text
浏览器 → https://sub2api.example.com
        ├─ 原有路径          → Sub2API（保持原部署）
        ├─ /ext/app/*        → Ops 前端
        ├─ /ext/api/*        → Ops 后端
        └─ /ext/auth/*       → Ops 后端 Bootstrap

Ops 后端 → Sub2API /api/v1/auth/me（只在 Bootstrap 时校验身份）
Ops 后端 → 自己的 PostgreSQL、MinIO
```

“同一台服务器”不等于“同一域名”。浏览器应始终通过 Sub2API 的 `https://` 域名进入 iframe；不要把 `http://VPS-IP:8088` 作为自定义菜单 URL。Ops Session Cookie 的路径是 `/ext`，生产环境使用 Secure Cookie；同域 HTTPS 可以避免跨站 iframe Cookie 限制。外部不要直接开放 PostgreSQL、MinIO、Ops 后端端口。

Ops 后端配置中的 `SUB2API_BASE_URL` 是**容器主动请求 Sub2API**时使用的地址，与用户浏览器看到的菜单 URL 是两回事。推荐先填现有 HTTPS 域名，并按部署手册检查容器内连通性；若回连失败，再使两套 Compose 共享一个 Docker 网络，填写 Sub2API 的实际服务名和容器端口。共享网络应写入双方 Compose 配置，以便容器重建后仍然存在；不要依赖一次性的 `docker network connect` 命令。

## 2. 配置现有域名的反向代理

若现有 HTTPS 入口是**宿主机 Nginx**，且 Ops 前端、后端分别绑定本机 `127.0.0.1:8088`、`127.0.0.1:8090`，把以下三个 `location` 加入 Sub2API 域名对应的 `server {}`。`proxy_pass` 不带 URI 后缀，以保留原始 `/ext/...` 路径：

```nginx
location ^~ /ext/app/ {
    proxy_pass http://127.0.0.1:8088;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location ^~ /ext/api/ {
    proxy_pass http://127.0.0.1:8090;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 25m;
}

location ^~ /ext/auth/ {
    proxy_pass http://127.0.0.1:8090;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    access_log off;
    add_header Cache-Control "no-store" always;
}
```

`/ext/auth/bootstrap` 请求 URL 会短暂包含 Sub2API token；`access_log off` 防止这一段请求的完整查询字符串进入此层访问日志。如果前面还有 CDN、WAF、面板代理或另一层 Nginx，也要在那些层关闭或脱敏 `/ext/auth/` 的查询参数日志。不要把实际 token 写进测试命令、截图或故障报告。

如果现有 Nginx 本身运行在 Docker 容器里，`127.0.0.1` 指 Nginx 容器自身，不能直接套用上例。应将 Nginx 与 Ops 服务接入同一 Docker 网络，把代理目标改为 `http://ops-frontend:80`、`http://ops-backend:8090`；也可按现有容器编排方式提供稳定的内部 DNS 名称。仓库中的 [Nginx 参考配置](../nginx/ext.conf.example)使用了这类容器服务名，其中 `map`/`log_format` 属于 `http {}` 层，三个 `location` 才属于 `server {}` 层，不能整份放进同一个代码块。

若使用 Caddy、Traefik 或服务器面板反代，建立等价的三条同域路径规则即可。不要把 `/ext/` 路径前缀剥掉。保留 Sub2API 原有 `/`、`/api/` 等转发规则。

检查并重载 Nginx：

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -fsS https://sub2api.example.com/ext/api/health
curl -fsS -o /dev/null -w '%{http_code}\n' https://sub2api.example.com/ext/app/
```

健康接口应返回 `{"ok":true,"service":"ops-extension"}`；前端应返回 `200`。此时直接打开前端业务路径未必有登录会话，须通过下一步菜单的 Bootstrap 进入。确认现有站点响应头没有对 `/ext/app/*` 设置 `X-Frame-Options: DENY` 或不允许同源 iframe 的 `Content-Security-Policy`；若有，只调整这些扩展路径所需的嵌入策略，不要移除全站安全策略。

## 3. 在 Sub2API 新增四个自定义菜单

以 Sub2API 官方前端当前的设置结构为准：管理员进入**系统设置 → 常规设置 → 自定义菜单**，为每项填写菜单名称、可见范围和完整 URL；`page_slug` 留空，选择 URL/iframe 页面，建议勾选“隐藏新标签页打开按钮”。设置页面还可上传 SVG 图标、调整菜单顺序。具体字段见 [Sub2API 设置页面源码](https://github.com/Wei-Shaw/sub2api/blob/a3eb7ef302961cba716dc78b39b93b60c467db0e/frontend/src/views/admin/SettingsView.vue)。

| 菜单名称 | 可见范围 | 完整 URL |
| --- | --- | --- |
| 我的工单 | 用户（`user`） | `https://sub2api.example.com/ext/auth/bootstrap?next=/ext/app/tickets` |
| 工单管理 | 管理员（`admin`） | `https://sub2api.example.com/ext/auth/bootstrap?next=/ext/app/admin/tickets` |
| 报账管理 | 管理员（`admin`） | `https://sub2api.example.com/ext/auth/bootstrap?next=/ext/app/admin/expenses` |
| 费用报表 | 管理员（`admin`） | `https://sub2api.example.com/ext/auth/bootstrap?next=/ext/app/admin/reports` |

把示例域名统一替换为站点的真实 HTTPS 域名。**不要**手工在 URL 中追加 `token`、`user_id`、`theme` 或 `lang`，Sub2API 的 [iframe URL 构造器](https://github.com/Wei-Shaw/sub2api/blob/a3eb7ef302961cba716dc78b39b93b60c467db0e/frontend/src/utils/embedded-url.ts)会附加这些参数。不要把菜单 URL 改为 `/ext/app/...`：Ops 的 [Bootstrap 代码](../backend/app/auth/bridge.py)需要先校验 Sub2API 身份并签发自己的会话。Ops 内的“主数据”从“报账管理”页面进入，不需要第五个菜单。

## 4. 登录、权限和主题的实际流程

1. 用户登录 Sub2API，点击自定义菜单。Sub2API 在 iframe URL 中附加短暂使用的身份令牌、用户 ID、已解析的浅色/深色主题、语言和 `ui_mode=embedded`。
2. Ops 的 `/ext/auth/bootstrap` 使用该令牌请求 `SUB2API_BASE_URL/api/v1/auth/me`，确认用户状态和 `user`/`admin` 角色，建立 Ops Session，然后跳转到不含令牌的 `/ext/app/...` 页面。Ops 不保存 Sub2API Bearer token。
3. Ops 的 API 使用自身 Session Cookie；普通用户可以处理自己的工单，报账、报表和管理功能需要 Sub2API `admin` 角色。管理员在 Sub2API 中变更用户角色/状态后，用户须重新进入菜单刷新 Ops 的身份快照。
4. 菜单每次进入都会重新走 Bootstrap。Ops Session 默认有效期为 2 小时；到期或需要刷新身份时，重新点击 Sub2API 菜单。宿主切换浅色/深色/跟随系统时会更新 iframe 地址，Ops 按传入主题重新显示；iframe 重载可能使未保存的表单内容丢失。

当前实现只依赖 Sub2API 的自定义菜单和 `/api/v1/auth/me`，两套应用仍分别发布。Sub2API 升级后，应回归检查自定义菜单参数及 `/auth/me` 响应格式；无需把 Ops 代码合并进 Sub2API 仓库。[Sub2API 自定义页面实现](https://github.com/Wei-Shaw/sub2api/blob/a3eb7ef302961cba716dc78b39b93b60c467db0e/frontend/src/views/user/CustomPageView.vue)

## 5. 联调验收

在真实 HTTPS 域名下，用一名普通用户和一名管理员分别操作：

| 检查项 | 预期 |
| --- | --- |
| 普通用户点击“我的工单” | 直接看到工单列表，可创建工单；没有第二排 Ops 模块导航。 |
| 管理员点击四个菜单 | 工单管理、报账管理、费用报表均能打开；主数据可由报账页进入。 |
| 浅色、深色、跟随系统 | iframe 内容与宿主的实际明暗模式一致；切换会重新加载页面。 |
| 工单和报账附件 | 上传、下载成功；上传请求未被反代的大小限制拦截。 |
| 浏览器开发者工具 | Bootstrap 返回 302，后续业务页面 URL 不带 token，`ops_session` 的 Path 为 `/ext` 且 HTTPS 下为 Secure。 |
| 服务端访问日志 | `/ext/auth/` 的原始查询参数不被记录；其他页面与 API 不出现 token。 |

## 6. 常见问题

| 现象 | 检查方向 |
| --- | --- |
| 菜单没有出现 | 自定义菜单是否保存、可见范围是否正确、Sub2API 当前用户是否拥有对应角色。 |
| iframe 显示 404 或空白 | `/ext/app/`、`/ext/api/`、`/ext/auth/` 的路由是否保持原路径；前端 SPA 是否回退到 `/ext/app/index.html`。 |
| `IDENTITY_UNAVAILABLE` | Ops 后端容器能否连接 `SUB2API_BASE_URL`；DNS、TLS、共享网络和实际服务端口。 |
| `INVALID_TOKEN` 或登录错误 | 菜单是否指向 Bootstrap，Sub2API 登录是否仍有效；重新登录并点击菜单。 |
| 打开后又回登录错误页 | HTTPS/Secure Cookie、浏览器 Cookie、是否误用不同域名或不同端口。 |
| 管理员被退回工单页 | `/api/v1/auth/me` 返回的角色是否为 `admin`；重新进入菜单刷新快照。 |
| 浅深色没有同步 | Sub2API 是否把 `theme` 参数传给 Bootstrap；`/ext/app/theme-init.js` 能否正常加载。 |
| 附件上传返回 413 | Nginx 或更前面的代理上传大小限制；本例为 `25m`，应用文件限制为 20 MB。 |

对接完成后，日常升级 Ops 只需更新独立服务栈；Sub2API 的四个自定义菜单继续指向相同的 `/ext/auth/bootstrap` 路径。
