# 组件规范

组件是工作空间级可复用 Vue 资产。创建或修改组件前先执行 `wp standards component`，并读取组件详情、最新草稿、发布版本和依赖。

## 组件类型

- **页面组件**：封面、目录、章节页、重复内容页模板、报告页模板、数据页模板、页面骨架或其它整页视觉模板；以 `DefaultContainer` 或已发布页面骨架为根，具备独立整页画布能力，不依赖父页面偶然提供的高度。
- **内容组件**：卡片、图表、指标组、表格、资源展示块和普通业务区块；必须在 `preview_schema.props` 中至少声明 `width`、`height`、`minHeight` 或 `aspectRatio` 之一。
- **原子组件**：按钮、徽章、头像、页码、图标、Logo、分割线等单一职责小单元；优先使用 `size`、`density`、`variant`、`tone` 等语义参数。

只为当前页面的一次性包装不要抽成组件。若多个页面共享标题区、眉题/导航、主体区和辅助区的空间关系，应创建或复用页面组件，即使正文、图表和数据不同；若只有卡片、图表或指标模块重复，则创建内容组件。组件变化应由 props/slots 表达，并保持主题中立，不把当前项目文案、画布尺寸或 palette 写死。

## 源码与 preview schema

组件 content 必须是完整、可运行的 Vue 3 SFC，遵守 [页面源码规范](./source-standards.md) 中的 Runtime、Tailwind、主题、字体、资源边界和动态资源名规则。

组件展示三维模型时使用 `AssetModel`，只引用真实 `model3d` 资源 `name`，容器声明明确宽高；相机索引与显式位置/目标互斥，位置和目标必须成对。`preview_schema` 的 presets 若设置模型 `name`，必须使用真实资源，不要编造模型名或传入 URL、路径、GLB 文本。

组件展示音频时使用 `AssetAudio`，只引用真实 active `audio` 资源 `name`，容器声明明确宽高。内容音频使用 `purpose="content"`，组件不暴露 `autoplay`；旁白只在 `capabilities.slideshow.audio.page_narration=true` 时使用，不能设置 `loop`，同一预览实际页面最多一个旁白目标。`preview_schema` 的 presets 若设置音频 `name`，必须使用真实资源；交互音效只通过 `useAudioCue.v1` 的 `interaction.*` key，不在组件中读取或复制项目 cue 绑定。能力未开放时，不要把旁白或 cue 音效作为组件默认体验或宣称可用。

`preview_schema` 必须是合法 JSON 对象，结构通常为：

```json
{
  "props": {},
  "slots": {},
  "mocks": {},
  "presets": []
}
```

- `props` 字段与 `defineProps` 一致，字段的 `type`、`label`、`default` 和 `options` 必须真实可用；预览值不要放在 Schema 根节点。
- 支持的 prop 类型以当前平台规范为准，常见为 `string`、`textarea`、`number`、`boolean`、`select`、`json`。
- `slots` 使用声明式 `text`、`html`、`component` 节点；slot component 只能引用版本化 Runtime Kit 或已发布工作空间组件，不能引用 Runtime 私有路径或动态 import。
- 引用工作空间组件（作为 slot component 或在组件源码中引用子组件）时，必须使用 `@workspace-components/<component_code>/v/<version_no>`，且被引用组件必须为已发布的正式版本（`current_version_no > 0`），禁止引用草稿或使用自增主键 ID。
- `mocks` 只保存 JSON/文本级静态值，不放函数、表达式、HTTP 请求或 component-preview 内部能力。
- `presets` 只写覆盖值；key 稳定、label 清晰，优先提供 2～3 个高质量真实场景。
- 资源名、默认值和 mock 数据必须来自真实工具结果；没有资源时使用空值或明确占位，不编造名称。音频 presets 只能引用真实 `audio` 资源，不能把 URL、本地路径或 base64 写进 `name`。

## 创建、编辑和发布

```bash
wp component get <component_id>
wp component dependencies <component_id>
wp component validate <component_id> --mode content --source-file .tmp/web-presentation/component-<component_id>.vue
wp component edit <component_id> \
  --base-version-no <base_version_no> \
  --base-draft-hash <draft_hash> \
  --edits-file .tmp/web-presentation/edits-<component_id>.json \
  --idempotency-key <key>
wp component publish <component_id> --idempotency-key <key>
```

创建组件使用 `wp component create`，同时提供 `--type`、完整 SFC 和必要的 `--preview-schema-file`。修改源码、`component_type` 或 `preview_schema` 前必须读取最新草稿和乐观锁基线；版本/编辑锁冲突时重新读取并生成 edits，不能静默覆盖。

组件写入会自动执行 Runtime 编译、默认态、preset 渲染和布局检查；独立 `component validate` 用于候选预检或需要更详细诊断。发布前确认源码、依赖、默认态、presets 和校验结果，发布后页面和其它组件引用正式版本。
