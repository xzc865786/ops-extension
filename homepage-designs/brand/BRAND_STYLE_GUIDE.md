# 汇码智能 HUIMA INTELLIGENCE — Brand Style Guide v1

## 1. 品牌核心

定位：AI API 平台、软件服务、定制开发。  
视觉关键词：科技、专业、创新、克制、现代。  
品牌角色：技术底座提供者 / 高端技术工作室。

## 2. Logo 体系

### 主标识
- `assets/huima_symbol_master_v3.svg`
- 三个石墨色模块围绕智能青核心汇聚。
- 主标识的几何结构已锁定，不再通过图像生成模型重新解释。

### 横版组合
- 浅色背景：`assets/huima_lockup_horizontal_light.svg`
- 深色背景：`assets/huima_lockup_horizontal_dark.svg`
- 官网 Header、API 平台、名片优先使用横版。

### 竖版组合
- `assets/huima_lockup_stacked_light.svg`
- `assets/huima_lockup_stacked_dark.svg`
- 用于封面、方形区域或纵向版式。

### Micro Mark
- `assets/huima_symbol_micro_v1.svg`
- 主要用于约 16px favicon / 极小界面尺寸。
- 只放大核心视觉权重，不改变品牌概念。

## 3. 安全空间

Logo 四周至少保留 **0.25H** 的净空，其中 H 为标识组合高度。  
不要让导航文字、边框、照片主体或其他图形侵入安全区。

## 4. 推荐尺寸

- 官网 Desktop Header：220–280px 宽。
- 紧凑 Header：约 180px。
- 横版组合 <150px 时，建议切换为 Symbol Only。
- 标准 Symbol：建议不低于 24px。
- 16px：使用 Micro Mark。

## 5. 标准颜色

| Token | Hex | 用途 |
|---|---|---|
| Graphite | `#2B2E33` | Logo、主文字、核心界面 |
| Intelligence Teal | `#17CFD8` | Logo 核心、活动状态、少量重点 |
| White | `#FFFFFF` | 深色背景反白 |
| Neutral Light | `#F5F7F8` | 辅助背景 |

智能青是品牌强调色，不作为白底正文的大面积文字颜色。

## 6. 背景规则

浅色背景：
- Graphite 外部结构
- Graphite 字标
- Teal 核心

深色背景：
- White 外部结构
- White 字标
- Teal 核心

## 7. 禁止事项

不要：
- 拉伸、压扁、倾斜 Logo。
- 改变三个外部模块之间的比例。
- 随意改变核心青色。
- 增加渐变、发光、投影、浮雕、金属质感。
- 给 Logo 套描边。
- 在复杂照片上直接放 Logo 而不保证对比度。
- 把横版 Logo 缩得过小仍强行显示英文辅标。
- 重新通过生图模型生成官方 Logo。

## 8. 开发接入

颜色与尺寸 Token：
- `tokens/brand-tokens.css`
- `tokens/brand-tokens.json`

网站 Header 示例：
- `examples/website-header-example.html`
