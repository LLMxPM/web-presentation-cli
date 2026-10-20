# 资源与设计系统

资源、主题、字体和样式是页面生成的输入，不是代码完成后的装饰。先确定内容表达与渲染能力；需要共享资产时查询真实对象，再决定引用、创建或修改。

## 按内容选择 Runtime 渲染能力

生成页面或组件时，遇到图片、音频、数学公式、数据图表、流程图或三维模型，优先使用对应 Runtime Kit 渲染组件。这个选择从内容需求开始；没有现成资源时，文本渲染组件也可以直接接收内容。

| 内容表达 | 资源的 `render_type` | 优先使用 |
| --- | --- | --- |
| 图片、照片、插图 | `image` | `AssetImage` |
| 视频 | `video` | `AssetVideo`，必要时使用真实 poster |
| 音频、旁白 | `audio` | `AssetAudio`，内容音频手动播放；旁白需 `page_narration` 能力开放 |
| 三维模型 | `model3d` | `AssetModel`，只引用自包含 GLB 资源和真实 `name` |
| Draw.io 图 | `drawio` | `AssetDrawio`，内容为 Draw.io XML |
| 流程图、关系图等 Mermaid 图 | `mermaid` | `AssetMermaid`，内容为 Mermaid 源码 |
| 柱状图、折线图、饼图等数据图表 | `chart` | `AssetChart`，内容为 ECharts option JSON 文本 |
| 数学公式 | `formula` | `AssetFormula`，内容为 LaTeX 文本 |
| 图标 | `icon` | `Icon` |
| 自定义图片布局或背景 | `image` | `useAssetSrc` / `useAssetBackground` 解析资源 URL |

通过 `wp runtime-kit list` 发现当前能力，只对选中的项执行 `wp runtime-kit get <item>`，读取 `import_path`、`usage`、`constraints` 和 `preview_schema.props`；路径和参数以当前返回为准。Runtime 负责 ECharts、公式、Mermaid 和三维模型等渲染器的初始化与生命周期，页面负责内容、数据和布局。

## 图标发现与契约读取

按“查图标 → 读 Icon 契约 → 使用真实 name”执行：

```bash
wp --json asset list --type icon --page 1 --page-size 50
wp --json asset list --type icon --keyword navigation --page 1 --page-size 50
wp --json runtime-kit get Icon.v1
```

保留资源响应的 `total`、`page`、`page_size` 和 `items`，按分页继续查询；关键词未命中或第一页没有目标不代表工作空间没有图标。只引用当前工作空间的 active 资源。`Icon.v1` 是渲染契约，`home` 等示例不是内置资源保证；没有合适资源时，按当前任务授权创建安全 SVG 图标资源并使用返回的真实 `name`，不要用整页渲染逐个试探名称。独立 Runtime 可使用其自身图标配置，平台内容使用工作空间资源。

Runtime Kit 详情输出保留完整契约。阅读时必须保留 `import_path`、`usage`、`constraints`、`preview_schema.props`（能力详情中的字段可能位于 `capability` 下）；如需缩小数据，按这些字段投影。不要使用 `json.dumps(... )[:N]` 或只读取前若干字符。缺少关键字段或出现省略标记时，补读该项完整详情后再写源码。

## 三维模型


三维模型使用公开的 `model3d` 资源和 Runtime Kit 的 `AssetModel`；Three.js 只属于 Runtime 内部实现，页面和组件不直接初始化 Three.js。

```bash
wp --json asset list --type model3d
wp --json asset get <asset_id>
wp runtime-kit get AssetModel.v1
```

- 首期只接受自包含 GLB；使用真实资源 `name`，不向 `AssetModel` 传 URL、本地路径、GLB 文本或 base64。资源含动画数据不代表支持动画播放，当前展示静态姿态。
- 使用前读取 `AssetModel` 最新契约和资源的场景/相机摘要，按“查询模型 → 读取渲染契约 → 配置视角”执行；相机索引与显式 `cameraPosition`/`cameraTarget` 互斥，位置和目标必须成对且不重合。
- 容器必须通过完整静态 class 声明明确宽高，例如 `w-full h-80`；不要给 `AssetModel` 传 `style`，也不要用 `min-h` 或内容自由高度作为尺寸来源。
- 工作空间没有合适模型时，不编造资源名，也不要用文本工具伪造 GLB。用户已提供本地 GLB 时，将其保存到 `.tmp/web-presentation/` 后执行 `wp asset upload --type model3d`，再按返回的真实 ID/name 引用；只有缺少可用模型文件时，才请求用户补充。
- 上传、替换和下载原始文件：

```bash
wp asset upload .tmp/web-presentation/product.glb --type model3d --name product --idempotency-key <key>
wp asset replace <asset_id> .tmp/web-presentation/product-v2.glb --expected-file-hash <current_file_hash> --idempotency-key <key>
wp asset download <asset_id> --output .tmp/web-presentation/product.glb
```

- 替换会更新引用该资源的当前与历史页面预览；独立构建保留当次资源快照。替换后重新截图确认模型、材质、光照和视角，不需要修改页面源码中的资源名。

```vue
<!-- 文件功能：演示按真实资源名和显式相机配置渲染三维模型。 -->
<AssetModel
  name="product"
  :camera-position="[0, 1, 4]"
  :camera-target="[0, 0, 0]"
  class="w-full h-80 rounded-lg border border-border p-0 bg-transparent overflow-hidden"
/>
```

## 音频、旁白与交互音效

音频使用 `asset_type=audio`、`render_type=audio` 的工作空间资源，并通过 Runtime Kit 的 `AssetAudio` 传真实 `name`。平台首版不转码，推荐 MP3；允许 `.mp3`、`.m4a`、`.aac`、`.ogg`、`.wav`，扩展名与 MIME 必须同时匹配。音频是内容资源，不可文本编辑，不参与图片宽高比回填。

先读取能力，再决定做内容音频、旁白还是 cue：

```bash
wp --json workspace capabilities
wp --json asset list
wp --json asset get <asset_id>
wp runtime-kit get AssetAudio.v1
wp runtime-kit get useAudioCue.v1
```

`capabilities.slideshow.audio` 给出三个独立开关：`audio_assets`、`page_narration`、`audio_cues`。当前阶段可能只开放 `audio_assets`；能力未开放的用途不得生成、绑定或向用户宣称。

```bash
wp asset upload .tmp/web-presentation/chapter-01.mp3 --type audio --name chapter-01 --idempotency-key <key>
wp asset download <asset_id> --output .tmp/web-presentation/chapter-01.mp3
wp asset replace <asset_id> .tmp/web-presentation/chapter-01-v2.mp3 \
  --expected-file-hash <current_file_hash> --idempotency-key <key>
```

如果当前 CLI 的 `asset upload --type` 不接受 `audio`，停止并报告 CLI 需要升级；不要用其他资源类型绕过，也不要直接调用未公开接口。`asset replace` 必须携带最新 `file_hash`，基线不匹配返回 `ASSET_VERSION_CONFLICT`；替换保留资源 ID、名称和类型，并同步影响当前与历史页面预览，独立构建保留当次快照。

内容音频由用户手动播放，页面不写 `autoplay`：

```vue
<!-- 文件功能：演示通过工作空间音频资源逻辑名渲染可手动播放的内容音频。 -->
<AssetAudio name="chapter-01" purpose="content" controls class="w-full h-16" />
```

页面旁白只在 `page_narration=true` 时使用：

```vue
<!-- 文件功能：演示能力开放时声明页面旁白目标，不设置 loop 或 autoplay。 -->
<AssetAudio name="chapter-01-narration" purpose="narration" :volume="0.9" class="w-full h-16" />
```

- 同一实际渲染页面最多一个 `purpose="narration"` 目标；旁白禁止 `loop=true`，组件不暴露 `autoplay`。
- 旁白自动播放只发生在真实放映执行上下文；普通预览必须先由用户手势试听。
- `advance.mode=media_end` 时旁白与其他参与媒体进入同一完成集合；`timer` 可能在旁白结束前翻页，`manual` 不因旁白结束翻页。制作旁白页时优先使用 `media_end`，并在保存前确认服务端已开放该模式。
- 不要用截图证明旁白已经播放；截图只能证明资源名、播放器布局和页面结构。真实声音与自动播放需要在用户手动操作的预览或放映中验证。

交互音效只使用公开 composable 和语义 cue key：

```ts
// 文件功能：演示通过 Runtime Kit composable 请求播放项目绑定的交互音效。
import { useAudioCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'

const { playCue } = useAudioCue()
playCue('interaction.confirm')
```

- 只接受 `interaction.*` key；`transition.forward` 和 `transition.backward` 由 Runtime 切页通道独占，页面调用返回 `unavailable`。
- 只在 `audio_cues=true` 时绑定和承诺音效；`played`、`skipped`、`unavailable` 只是同步状态，业务逻辑不得等待播放完成或依赖其副作用。
- 预览、组件预览、截图、检查和导出上下文为 no-op；没有 cue 绑定、会话静音或加载失败时也不阻塞业务。
- cue 绑定属于项目级音频设置，不是页面源码资源；不要向 `useAudioCue` 传 URL、资源 ID、音量或 `Audio` 实例。

项目音频设置通过专用命令读写；cue 绑定只接受当前项目所在工作空间内的 active `audio` 资源：

```bash
wp --json project audio get <project_id>
wp --json project audio update <project_id> --audio-file .tmp/web-presentation/audio.json --idempotency-key project-<id>-audio
wp --json project audio clear <project_id> --idempotency-key project-<id>-audio-clear
```

`get` 返回服务端读取模型，绑定带 `asset_name`、`asset_type`、`asset_status` 等只读展示字段；`update` 只接受写模型：

```json
{
  "master_volume_percent": 100,
  "narration_volume_percent": 90,
  "effects_volume_percent": 30,
  "cue_bindings": [
    { "key": "interaction.confirm", "asset_id": 51, "gain_percent": 80 }
  ]
}
```

- `update` 必须提交完整对象：三段音量与 `cue_bindings` 都必填，未知字段、只读字段、`null` 和缺失音量会被本地拒绝；显式空 `cue_bindings` 表示清空绑定。音量都是 0–100 的严格整数，cue key 使用小写点分段且在同一项目内唯一；跨工作空间、非音频资源或重复 key 应视为整批失败，不要部分重试。
- `clear` 只删除 cue 绑定并保留三段音量，由服务端单事务执行；不要用 `get` 后 `update` 的读改写模拟清空，否则会覆盖期间其它客户端的音量更新。
- 含非空 `cue_bindings` 的写入（包括 `project audio update`、`project update` 和 `project configuration update`）要求 `capabilities.slideshow.audio.audio_cues=true`；能力缺失或为 false 时 CLI 直接失败，不发送写入。`get` 仍可读取历史值，`clear` 在能力关闭时仍可降级治理。

## 共享资源与直接内容

- **引用共享资源**：先查询当前工作空间的 active 资源，关注 `name`、`asset_type`、`render_type`、`content_editable`、版本/状态、标签和近似宽高比；向对应组件传真实逻辑名 `name`。图片和音频上传后也使用返回的真实 name。
- **直接渲染文本**：`AssetFormula`、`AssetChart`、`AssetMermaid` 和 `AssetDrawio` 支持 `content`；一次性内容可以直接传入 LaTeX、ECharts option JSON、Mermaid 源码或 Draw.io XML。`content` 是字符串；图表配置对象先用 `JSON.stringify` 转成文本，公式在脚本字符串中注意 LaTeX 反斜杠转义。
- **决定是否创建资源**：已有合适资产优先复用；内容需要跨页共享或独立维护时创建文本资源，再按 name 引用。本页的一次性公式或图表可以直接传 content，无需为每个内容块新增资产。

文本渲染组件按所选模式传 `name` 或 `content`；两者同时传入时 content 优先。资源名规则适用于 name 模式，直接内容模式不需要编造资源名。实际图表数据须来自用户材料或 CLI 真实结果；以下片段只演示调用方式，资源名和数据均为示意，实际 import 必须从 Runtime Kit 查询。

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

`Icon`、`AssetImage`、`AssetVideo`、`AssetAudio`、`AssetModel` 等组件的 `name` 优先使用字符串字面量或同一 Vue 文件顶层的静态枚举，便于离线构建精确收集资源依赖。确需动态资源名时，候选名称必须来自当前工作空间 active 资源，并在项目 `build_extra_assets_json.asset_names` 中补齐所有可能引用；保存或预览成功不代表独立构建包含这些资源。`useAssetSrc(() => props.imageName)` 仍是 props 资源名的正确写法，但不免除动态资源名的构建额外资源要求。图标名必须等于资源逻辑名，优先查询现有图标再创建。

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

非 SVG 位图、video、audio、font、model3d 等使用 `asset upload`；`model3d` 只接受自包含 `.glb`，`audio` 只接受受支持的音频扩展名和 MIME。更新已有二进制资源必须用 `asset replace` 携带 `--expected-file-hash`，不能走通用覆盖。不要用 `asset create` 伪造二进制内容，也不要把 URL、本地路径或 base64 当成可信上传附件参数。生成或上传后用返回的真实 name/ID 和 render_type。

## 主题

主题负责共享视觉语义、色板、Logo 与字体绑定。多页统一视觉时优先使用主题类，不要在每页硬编码品牌色；现有主题与用户目标不匹配时再复制或创建主题。

- 创建主题必须指定稳定、未占用的 `key`；key 创建后不可修改。
- 主题维护支持通过 `--payload-file` 传入名称、说明、色板（`palette`）、图片（`logo_asset_id`、`invert_logo_asset_id`、`project_icon_asset_id`）及标题/正文/代码三槽字体配置。
- 图片槽位必须传入当前工作空间 active 状态的真实资源 ID；`project_icon_asset_id` 必须是 `asset_type=icon` 资源；显式传入 `null` 表示清空，省略该键表示保持现状。
- 字体槽位通过 `heading_font_family_id` / `heading_font_preset`、`body_font_family_id` / `body_font_preset`、`code_font_family_id` / `code_font_preset` 配置：
  - 若绑定工作空间自定义注册的字体族，必须传入 `family_id`（通过 `wp font family list` 获取），严禁混传 `asset_id` 或 `font_id`；
  - 若使用预设系统字体族，传入对应 preset（如 `sans`、`serif`、`mono`、`system-ui`）；
  - 清空自定义字体绑定时将对应的 `family_id` 显式设为 `null`；省略键表示保持现状。
- 主题 palette 使用公开的 `text`、`background.default/invert`、`border`、`link` 和 `accent` 结构；不要把 Tailwind 类名、`background-subtle` 或 `tertiary` 当成主题 Schema 字段。

## 字体

字体管理包含字体面（Font Face）与字体族（Font Family），形成规范生命周期：

1. **上传字体文件**：运行 `wp asset upload <file> --type font --name <name>` 获得资源 `asset_id`。注意上传资源仅是二进制素材，不等于已注册字体；
2. **注册字体面**：运行 `wp font register <asset_id> --family-name <name> --display-name <label>` 注册字体面并关联到指定字体族（自动创建新族或归入同名已有族），获得 `font_id` 与 `family_id`。支持通过 `--weight` 与 `--style` 区分字重和字形；
3. **管理字体族**：通过 `wp font family list` 查看工作空间预设系统字体族与自定义注册字体族；需要时可通过 `wp font family rename <family_id> --name <new_name>` 调整族展示名称；
4. **绑定与消费**：将 `family_id` 绑定至主题对应字体槽位；页面中优先使用 `font-heading`、`font-body`、`font-code` 主题语义类；页面或组件消费非主题自定义字体时使用 `useAssetFontFamily(family_id)`。切勿在页面 CSS 中手写 `@font-face` 或硬编码字体文件 URL。

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
