# 页面源码规范

本参考保留稳定的页面代码判断，适用于通过 `wp` 创建或编辑页面源码。执行具体任务前仍需运行 `wp standards page`，以当前 Backend 返回的公开约束为准。

## 通用源码契约

- `page_content` 必须是完整、可运行的 Vue 3 SFC，不是 HTML 片段、Markdown、JSON 或解释文字。
- 优先使用 `<script setup lang="ts">`、Composition API、顶层静态 import、Vue 响应式能力和 Tailwind 语义类。
- 不使用 Node API、服务端文件系统 API、远程脚本、未声明依赖、全局副作用或运行时动态 `import()`。
- 只能引用平台真实返回的版本化 Runtime Kit 能力、已发布工作空间组件、可见工作空间资源和自身代码。
- Tailwind class 必须以完整静态字符串出现在模板、脚本常量或顶层枚举映射中；禁止 `text-${tone}`、`from-${color}` 等运行时拼接。Arbitrary value 也要以完整静态类出现在源码中。

## 工作空间组件引用契约

- 页面源码引用工作空间组件时，统一使用已发布组件的版本化别名：
  ```ts
  import <ImportName> from '@workspace-components/<component_code>/v/<version_no>'
  ```
- 约束说明：
  - 路径中的编码必须是组件业务编码 `code`（如 `CMP20260503001`），不能使用自增 ID、本地相对路径或 `@/` 别名；
  - 版本号必须是当前大于 0 的正式发布版本 `current_version_no`，未发布或草稿状态的组件不可在页面中引用；
  - 导入标识符优先使用组件元数据中的 `import_name`（或展示名 PascalCase）；
  - 可直接通过 `wp component get <component_id>` 或 `wp component list` 查询已发布的 `import_path` 与 `import_statement`。

## 画布和布局

- 页面根部优先使用项目建议的已发布页面组件，其次是工作空间已发布页面组件，最后才是版本化 `DefaultContainer`。
- `DefaultContainer` 只提供真实画布宽高、定位上下文和裁剪，不是默认封面、内容页、卡片或页脚模板。
- 先规划整页标题区、主体区和辅助区，再实现具体元素；不要按网页文档的自然流从标题一路追加内容。
- 主要内容、分栏、卡片、图表、图片和公式必须有明确的宽高上下文、布局约束和 overflow 策略；依赖 `h-full` 的子元素必须有明确父级高度。
- 不用 `100vh`、`100vw`、页面滚动、`transform: scale` 或 `zoom` 逃避画布约束。固定高度和 `flex-1` 必须服务于已规划区域。
- 复杂性来自层级、比例、留白和信息关系，而不是无意义的渐变、阴影、圆角和装饰。

## 内容表达

- 每页围绕一个主要信息；标题尽量结论化，内容按阅读动线组织。
- 真实数字、事实、引用、Logo、客户名和资源名只能来自用户材料或 CLI 真实结果；精简文案不得改变条件、时间范围或不确定性，图形与数字保持一致。资料不足时说明缺口，占位只用于草稿或用户要求的待填项，不作为正式内容交付。
- 最终可见文字应服务于观众理解、必要操作或用户指定的表达；不主动添加无关的创作、实现、调试或预览说明。技术教学、必要操作指引和真实业务状态可以保留，不能按“循环播放”等关键词机械删除。
- 标题、标签、指标和短语列表默认不加句末句号，叙述正文正常使用标点，单句正文也可保留句号；保留语义性标点及忠实引用，遵循明确的用户或项目文案风格。详细规则和示例以 `wp standards page` 返回的当前规范为准。
- 检查依赖组件默认值、预览样例、图表和图片中的文字，避免样例泄漏与装饰性假信息；交互应真实可用，核心信息在截图和静态导出中仍需可读。
- 为长标题、长正文、缺图、空数据、加载和错误准备可读状态；不要让默认内容只在理想短文案下成立。
- 表格、时间线、密集数据、目录和长文可以有意顶部对齐；普通主体面板和稀疏卡片应在自己的区域内上下平衡。

## 内容渲染

图片、音频、数学公式、数据图表、流程图和三维模型优先交给对应 Runtime Kit 组件渲染，选择方式与示例见 [资源与设计系统](./design-system-and-assets.md)。共享资源使用查询得到的真实 `name`；支持直接内容的文本渲染组件可以使用 `content`，具体格式和属性以 `wp runtime-kit get <item>` 的返回为准。三维模型使用 `AssetModel`，只引用自包含 GLB 的真实 `model3d` 资源名，不传 URL、本地路径、GLB 文本或 base64。音频使用 `AssetAudio`，只引用真实 `audio` 资源名，不传 URL、本地路径或 base64。页面不自行初始化 ECharts、KaTeX、Mermaid、Three.js 或音频引擎，渲染器的生命周期由 Runtime 管理；页面源码仍负责构图和业务内容。

- 使用 `AssetModel` 前读取 Runtime Kit 当前契约和资源的场景/相机摘要，按“查询模型 → 读取渲染契约 → 配置视角”执行；相机索引与显式 `cameraPosition`/`cameraTarget` 互斥，位置和目标必须成对且不重合。容器必须用完整静态 class 声明明确宽高。
- 当前三维展示是静态姿态，资源含动画数据不代表支持动画播放。替换资源会更新当前与历史页面预览，独立构建保留当次资源快照；替换模型不需要修改页面源码中的资源名。
- 内容音频使用 `purpose="content"`，由用户手动播放；页面源码不得写 `autoplay`。旁白使用 `purpose="narration"` 前必须确认 `capabilities.slideshow.audio.page_narration=true`，且不得设置 `loop`、同一实际页面最多一个旁白目标、优先使用 `advance.mode=media_end`；能力未开放时不得生成旁白或宣称自动播放。
- 交互音效只通过 `useAudioCue.v1` 的 `interaction.*` key 请求，且只在 `audio_cues=true` 时承诺播放；预览、截图、检查和导出为 no-op，业务逻辑不得等待或依赖播放结果。不要向页面暴露项目级 cue 绑定或音量设置。
- 音频替换会更新当前与历史页面预览，独立构建保留当次资源快照；替换不需要修改页面源码中的资源名，但必须携带最新 `file_hash` 基线。
- `Icon`、`AssetImage`、`AssetVideo`、`AssetAudio`、`AssetModel` 等组件的 `name` 优先使用字符串字面量或同一 Vue 文件顶层的静态枚举。确需动态资源名时，候选名称必须来自当前工作空间 active 资源，并在项目 `build_extra_assets_json.asset_names` 中补齐所有可能引用；保存或预览成功不代表独立构建包含这些资源。`useAssetSrc(() => props.imageName)` 仍是 props 资源名的正确写法，但不免除该构建额外资源要求。

## 主题、字体与 Token

Runtime 主题语义颜色键是：

`primary`、`secondary`、`invert`、`background`、`background-subtle`、`background-invert`、`border`、`border-subtle`、`link`、`link-hover`、`link-visited`、`accent1` 至 `accent6`。

- `background-subtle` 是 Runtime 语义槽位，不是主题写入 Schema 的 `palette.background.subtle` 字段。
- 使用 `font-heading`、`font-body`、`font-code`。需要非主题字体时先 `wp font list`，再使用真实字体逻辑名和 `useAssetFontFamily`。
- 主题 Logo 优先使用版本化 `ThemeLogo`，只通过 `size` 控制等比高度；不要硬编码 Logo URL，通常也不要直接传 `width`、`height` 或 `fit`。
- 直接写 CSS 时只使用规范公开的 Runtime 桥接变量，例如 `--tw-color-text-primary`、`--tw-color-bg-default`、`--tw-color-bg-subtle`、`--tw-color-bg-invert`、`--tw-color-border-default`、`--tw-color-link-default`、`--tw-color-accent1`、`--tw-font-body`；不要猜测 `--color-*`。

## 页面上下文能力

页面需要页码、目录或导航数据时，用 Runtime Kit composable 读取数据，UI 由页面源码实现：

- `usePageSize`：当前真实画布宽高和 `pageStyle`；
- `useCurrentPage`：当前页码、总页数和标题；
- `useRouteCatalog`：路由目录数据；
- `usePageNavigation`：上下页/跳转控制；
- `useTheme`：高级场景读取主题 Logo 或样式。

这些能力不提供默认目录 UI、分页 UI、导航按钮、卡片或网页模板。真实 import path 必须来自 `wp runtime-kit list/get`，不得使用未带 `.vN` 的旧路径或 `@runtime-kit/internal/...`。

## 布局诊断的处理优先级

- `PAGE_RENDER_BOTTOM_OVERFLOW`：优先处理，表示固定画布底部可能裁切。
- `interior_gap`、`trailing_gap` 与 `sparse_top_aligned` 同时出现：检查 `mt-auto`、固定高度和顶部堆叠，通常改为局部垂直居中或重新规划容器。
- `empty_regions`：结合页面类型和构图判断；封面/章节页/海报式留白可能是有意的。
- `geometry_reliability=approximate`：旋转或 `clip-path` 只按外接矩形近似，必须结合截图判断。
- 正常多行正文、正常 `flex-wrap`、组合容器紧贴和有意装饰出血不要机械修复。
