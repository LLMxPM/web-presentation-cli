# 资源与设计系统

资源、主题、字体和样式是页面生成的输入，不是代码完成后的装饰。先确定内容表达与渲染能力；需要共享资产时查询真实对象，再决定引用、创建或修改。

## 按内容选择 Runtime 渲染能力

生成页面或组件时，遇到图片、数学公式、数据图表或流程图，优先使用对应 Runtime Kit 渲染组件。这个选择从内容需求开始；没有现成资源时，文本渲染组件也可以直接接收内容。

| 内容表达 | 资源的 `render_type` | 优先使用 |
| --- | --- | --- |
| 图片、照片、插图 | `image` | `AssetImage` |
| 视频 | `video` | `AssetVideo`，必要时使用真实 poster |
| Draw.io 图 | `drawio` | `AssetDrawio`，内容为 Draw.io XML |
| 流程图、关系图等 Mermaid 图 | `mermaid` | `AssetMermaid`，内容为 Mermaid 源码 |
| 柱状图、折线图、饼图等数据图表 | `chart` | `AssetChart`，内容为 ECharts option JSON 文本 |
| 数学公式 | `formula` | `AssetFormula`，内容为 LaTeX 文本 |
| 图标 | `icon` | `Icon` |
| 自定义图片布局或背景 | `image` | `useAssetSrc` / `useAssetBackground` 解析资源 URL |

通过 `wp runtime-kit list` 发现当前能力，只对选中的项执行 `wp runtime-kit get <item>`，读取 `import_path`、`usage`、`constraints` 和 `preview_schema.props`；路径和参数以当前返回为准。Runtime 负责 ECharts、公式和 Mermaid 等渲染器的初始化与生命周期，页面负责内容、数据和布局。

## 共享资源与直接内容

- **引用共享资源**：先查询当前工作空间的 active 资源，关注 `name`、`asset_type`、`render_type`、`content_editable`、版本/状态、标签和近似宽高比；向对应组件传真实逻辑名 `name`。图片上传后也使用返回的真实 name。
- **直接渲染文本**：`AssetFormula`、`AssetChart`、`AssetMermaid` 和 `AssetDrawio` 支持 `content`；一次性内容可以直接传入 LaTeX、ECharts option JSON、Mermaid 源码或 Draw.io XML。`content` 是字符串；图表配置对象先用 `JSON.stringify` 转成文本，公式在脚本字符串中注意 LaTeX 反斜杠转义。
- **决定是否创建资源**：已有合适资产优先复用；内容需要跨页共享或独立维护时创建文本资源，再按 name 引用。本页的一次性公式或图表可以直接传 content，无需为每个内容块新增资产。

文本渲染组件按所选模式传 `name` 或 `content`；两者同时传入时 content 优先。静态资源名的约束适用于 name 模式，直接内容模式不需要编造资源名。实际图表数据须来自用户材料或 CLI 真实结果；以下片段只演示调用方式，资源名和数据均为示意，实际 import 必须从 Runtime Kit 查询。

```ts
// 文件功能：演示在页面脚本中准备直接传给 Runtime 的公式与图表文本。
const formulaLatex = 'E = mc^2'
const chartOptionJson = JSON.stringify({
  xAxis: { type: 'category', data: ['Q1', 'Q2'] },
  yAxis: { type: 'value' },
  series: [{ type: 'bar', data: [120, 200] }],
})
```

```vue
<!-- 文件功能：演示页面模板中引用图片资源和直接渲染公式、图表的片段。 -->
<AssetImage name="product-hero" alt="产品主图" fit="contain" class="w-full h-64 overflow-hidden" />
<AssetFormula :content="formulaLatex" display-mode class="w-full h-20 text-primary overflow-hidden" />
<AssetChart :content="chartOptionJson" class="w-full h-96 overflow-hidden" />
```

## 资源名称与布局

先查资源，再写 name；不要根据文件名猜资源逻辑名。资源槽位匹配近似宽高比，完整展示优先 `contain`，只有用户明确要求时才 `cover`。

资源组件的外层必须通过完整静态 class 声明明确宽高，例如 `w-full h-64 rounded-lg border border-border overflow-hidden`。不要给 `Asset*` 传 `style`，不要只靠内容自由撑高、`min-h`、`max-height` 或外层裁切。`AssetImage` 的 class 控制外层图片框，`fit`/`position` 控制图片在框内的显示。

普通资源 URL 使用 `useAssetSrc`，背景使用 `useAssetBackground`；资源名来自 props 时使用 getter。`resolveResourcePath` 只适合非响应式代码，不要在 SFC 中直接解析动态 props。

`Icon` 和 `Asset*` 的 `name` 必须是字符串字面量，或来自同一 Vue 文件顶层的静态枚举；禁止 computed、函数返回、字符串拼接或条件表达式生成资源名。图标名必须等于资源逻辑名，优先查询现有图标再创建。

## 创建或上传资源

```bash
wp --json asset list
wp asset create \
  --payload-file .tmp/web-presentation/asset.json \
  --content-file .tmp/web-presentation/asset-content.txt \
  --idempotency-key <key>
wp asset upload .tmp/web-presentation/hero-image.png --type image --name hero-image --idempotency-key <key>
```

用户直接提供的原始文件保持其真实路径；智能体生成或落盘的 payload、文本和待上传文件写入 `.tmp/web-presentation/`。

文本资源创建前查询是否已有 active 同名资源。可创建的文本类型包括 SVG 图标/图片、Draw.io、Mermaid、Chart 和 Formula；内容必须是完整 UTF-8 文本，并按命令帮助和 Backend Schema 满足扩展名及安全约束。图标 SVG 不得包含 script、事件属性、`foreignObject` 或远程引用，优先使用 `currentColor`。

非 SVG 位图、video、font 等使用 `asset upload`；不要用 `asset create` 伪造二进制内容，也不要把 URL、本地路径或 base64 当成可信上传附件参数。生成或上传后用返回的真实 name/ID 和 render_type。

## 主题

主题负责共享视觉语义和色板。多页统一视觉时优先使用主题类，不要在每页硬编码品牌色；现有主题与用户目标不匹配时再复制或创建主题。

- 创建主题必须指定稳定、未占用的 `key`；key 创建后不可修改。
- 主题维护只使用 CLI 公开的名称、说明和色板字段；不要猜测或写入 Logo、字体、字体族 ID。
- 主题 palette 使用公开的 `text`、`background.default/invert`、`border`、`link` 和 `accent` 结构；不要把 Tailwind 类名、`background-subtle` 或 `tertiary` 当成主题 Schema 字段。

## 字体

先 `wp font list` 查询已注册字体。主题字体优先使用 `font-heading`、`font-body`、`font-code`；非主题字体必须是工作空间真实注册并下发的字体逻辑名，用 `useAssetFontFamily`，不要在页面 CSS 中写 `@font-face` 或硬编码字体文件 URL。

## 样式和项目配置

样式是可复用的项目展示配置模板，可能包括画布、基础字号、主题 key、样式规范和建议组件。应用样式到项目后形成独立快照；单项目微调直接更新项目 configuration，不要为一次性变化创建全局样式。

修改主题 key、画布、基础字号、样式规范或建议组件前，先读取最新 configuration。主题/字体/样式修改会影响多个页面或项目，写入前明确影响范围和用户目标。

## 主题 Token 消费示例

以下 palette 仅用于展示映射，实际写入必须先获取当前命令契约：

```json
{"text":{"primary":"#172033","secondary":"#526078","invert":"#ffffff"},"background":{"default":"#ffffff","invert":"#172033"},"border":{"default":"#ccd3df","subtle":"#e8ecf2"},"link":{"default":"#2563eb","hover":"#1d4ed8","visited":"#7c3aed"},"accent":["#2563eb"]}
```

| palette 来源 | 模板语义类示例 | 直接 CSS 的公开变量 |
| --- | --- | --- |
| text.primary | text-primary | --tw-color-text-primary |
| background.default | bg-background | --tw-color-bg-default |
| border.default | border-border | --tw-color-border-default |
| accent[0] | text-accent1 / bg-accent1 | --tw-color-accent1 |

```vue
<!-- 文件功能：在已提供画布尺寸的页面容器内消费项目主题。 -->
<template>
  <section class="h-full w-full bg-background p-12 text-primary font-body">
    <h1 class="font-heading text-4xl text-accent1">本页结论</h1>
    <p class="mt-6 border-t border-border pt-6 text-secondary">真实内容说明</p>
  </section>
</template>
```

普通模板优先完整静态语义类；需要直接 CSS 时使用 `color: var(--tw-color-accent1)` 等公开桥接变量。不要因变量不确定而硬编码品牌色。background-subtle 是 Runtime 派生语义槽位，不是可写 palette.background.subtle 字段。
