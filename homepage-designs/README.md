# 主页设计稿

为 `https://api.tysy.top`（汇码智能）首页准备的候选设计。每套都是**单个自包含 HTML 文件**：不引用任何 CDN 或 Google Fonts（国内访问不会卡住），直接用浏览器双击打开即可预览。

> **已选定：`03-holo-pop.html`（流光全息）**。已使用汇码智能官方品牌标识，模型展示为 Claude、GPT、DeepSeek、GLM。01、02 保留作参考，未同步这些改动。

## 汇码智能官方标识（`brand/`）

来自 *汇码智能 Brand Identity v1.0*（状态：LOCKED，2026-09-23）。页面**原样引用**官方矢量，没有修改几何与配色；规范见 `brand/BRAND_STYLE_GUIDE.md`。

| 文件 | 用途 |
|------|------|
| `brand/huima_horizontal_light.svg` | 浅色背景横版组合；首页导航与页脚使用 |
| `brand/huima_horizontal_dark.svg` | 深色背景反白横版 |
| `brand/huima_symbol_color.svg` | 纯图形标识（≥24px）；手机端导航与钥匙卡使用，也可设为 Sub2API 站点 Logo |
| `brand/huima_symbol_micro.svg`、`favicon.ico`、`favicon-32.png` | 16px 左右的小尺寸与浏览器图标 |
| `brand/brand-tokens.css` | 品牌色与尺寸 Token |

页面遵循的规范：

- 桌面导航使用横版组合，宽 172px（紧凑 Header 约 180px），四周净空 ≥ 0.25H。
- 手机导航空间不足 150px，切换为纯图形标识。
- favicon 使用 Micro Mark。
- 标识本身不加渐变、发光、阴影或旋转。
- 页面主文字色改为品牌 Graphite `#2B2E33`，青色强调改为 Intelligence Teal `#17CFD8`，深色面改为 `#171A1F`。全息渐变只用于页面装饰，不用于标识本身。

标识以内联 `<symbol>` 嵌入 HTML，去掉了 `id` 以便同页多次引用，其余与官方文件一致，所以页面仍是单文件，无需额外部署图片。

## 三套设计一览

| 文件 | 风格 | 关键词 | 标志性互动 |
|------|------|--------|------------|
| `01-neural-router.html` | **神经路由** · 深色赛博 | 霓虹、星空网格、数据流 | 首屏实时画布：请求从你的应用流经网关分发到各模型；上游随机出现 429，请求**中途改道**；点击画布可亲手发出一批请求。标题文字解码轮播，终端逐字演示三种协议。 |
| `02-pixel-arcade.html` | **像素街机** · 复古未来 | 8-bit、CRT 扫描线、合成波落日 | 可玩小游戏 *API Runner*：空格或点按让机器人跳过 429/503；撞上后不会 Game Over，而是「切换上游」换个颜色继续跑。另有选角、问号道具箱、CONTINUE 倒计时，并提供可开关的 8-bit 音效。 |
| `03-holo-pop.html` | **流光全息** · 明亮潮流 | 镭射卡、流体渐变、贴纸 | 3D 全息「万能钥匙卡」，随鼠标倾斜并折射光泽，点击翻面显示接入代码（附彩纸）。贴纸可以拖动；可以拨开关模拟上游故障，也可以拖滑杆设置配额。代码区可在 Claude Code、Python、Node、cURL 间切换，并支持一键复制。 |

三套设计共同具备：

- 手机端（390px）和桌面端均已检查，无横向滚动，也没有控制台报错。
- 遵循系统的「减少动态效果」设置：开启后改为静态画面。
- 画布动画在滚出视口或切到后台时暂停，节省 CPU。
- 读取 Sub2API 的登录态（`localStorage.auth_token`）：已登录用户看到「进入控制台」，管理员跳转 `/admin/dashboard`。
- 示例代码里的地址自动取当前域名，本地预览时回退为 `https://api.tysy.top`。

## 配置

每个文件 `<script>` 顶部都有一个 `SITE` 对象：

```js
const SITE = {
  name: '汇码智能',                  // 站点名，页面各处同步替换
  fallbackOrigin: 'https://api.tysy.top',
  links: {
    login: '/login', dashboard: '/dashboard', adminDashboard: '/admin/dashboard',
    models: '/model-plaza',
    docs: ''                        // 填入文档地址后才会显示「文档」入口
  }
};
```

`links` 中留空的项，其按钮会自动隐藏。

示例代码里的模型名（`claude-sonnet-4-5`、`gpt-5`、`deepseek-chat`、`glm-4.6`）只是占位，请改成站点实际开放的模型 ID。

## 部署到 Sub2API 首页

Sub2API 的「首页内容」（`home_content`）有两种模式：

1. **HTML 模式**：通过 `v-html` 插入，**`<script>` 不会执行**，本设计的动画和互动都会失效，所以**不要**直接粘贴 HTML。
2. **URL 模式**：内容填写以 `http(s)://` 开头的地址，Sub2API 会用全屏 iframe 加载它。**请使用这种方式。**

步骤：

1. 选定一个文件，放到服务器上，例如 `/var/www/tysy-home/home.html`。
2. 在主站 Nginx 的 `server {}` 中新增：

   ```nginx
   location = /home.html {
       root /var/www/tysy-home;
       add_header Cache-Control "no-cache";
   }
   ```

   确认该路径没有 `X-Frame-Options: DENY`，也没有禁止同源嵌入的 `frame-ancestors`（同源的 `SAMEORIGIN` 可以正常使用）。
3. Sub2API 管理后台 → 系统设置 → 首页内容，填入 `https://api.tysy.top/home.html` 并保存。

页面内所有按钮都带 `target="_top"`，在 iframe 中点击「登录」「进入控制台」会跳转整个窗口，而不是只在框内跳转。
