# 平台资源模型

Web Presentation 的核心边界是“当前工作空间”。所有资源归属、权限和引用都必须以 Backend 返回的真实 ID、稳定 name、版本和依赖为准。

## 对象关系

| 对象 | 作用 | 关键事实 | 常用 CLI 视图 |
| --- | --- | --- | --- |
| 工作空间 | 权限、数据隔离、共享资产边界 | PAT 必须有空间授权；Header/全局选项只是上下文 | `workspace list/use/capabilities` |
| 项目 | 一次演示、报告或内容集合 | 拥有页面；保存自己的画布、基础字号、主题、样式规范、建议组件、放映 `slideshow` 和音频 `audio_settings` 快照 | `project get`、`project configuration get`、`project slideshow get` |
| 路由树 | 页面顺序、分组、路径和可见性 | 修改路由不修改页面源码；替换是全量树操作 | `project route get/replace` |
| 页面 | 项目内实际内容页 | 保存 Vue SFC、标题/摘要/备注、当前版本和截图信息 | `page get/source/version/dependencies` |
| 工作空间组件 | 跨页面复用的 Vue 代码资产 | 草稿和发布版本分开；页面应引用已发布版本 | `component get/edit/publish/version/dependencies` |
| 资源 | 图片、视频、音频、三维模型、图标、SVG、Draw.io、Mermaid、Chart、Formula 和字体等 | 通过稳定 `name` 引用；`render_type` 决定 Runtime 渲染方式；三维资源带格式、场景、相机和动画摘要；音频不可文本编辑 | `asset list/get/content/download/replace` |
| 主题 | 共享视觉语义、色板与设计配置 | key 创建后不可改；支持配置色板、Logo/图标图片及三槽字体绑定 | `theme list/get/create/update/copy` |
| 样式 | 可复用的项目展示配置模板 | 应用到项目时复制成独立快照，后续不实时继承 | `style list/get/create/update/copy` |
| 字体 | 注册的字体面与字体族 | 支持字体面注册/修改与字体族管理，绑定到主题或组件 | `font list/get/register/update`、`font family list/get/rename` |
| Runtime Kit | 版本化公开运行时能力目录 | 不是工作空间资产，也不是通用 UI 库；只用真实返回的 `.vN` import path | `runtime-kit list/get` |
| Mutation Job | 页面/组件重任务的持久化执行记录 | 状态是 `pending/running/succeeded/failed/canceled` | `job get/wait/cancel/retry` |
| Preview Artifact | 项目或页面的短期交互预览 | 必须基于成功写入后的最新对象创建；`preview_url` 不代表正式发布 | `preview get` |

## 归属、引用和快照不要混淆

- 项目 configuration 是项目自己的展示快照；style 只是可复用模板，应用 style 后不会持续同步。
- 项目 slideshow 保存默认整页动画、翻页方式、循环与进入放映后的初始自动推进（`auto_start`）；路由节点可整组覆盖 `transition`/`advance`，`null` 表示继承。保存设置不代表已控制浏览器播放。
- 项目 audio_settings 保存主音量、旁白音量、音效音量与 cue 绑定；读取以项目配置返回的 `asset_name/asset_status` 为准，写入只接受当前工作空间 active `audio` 资源的 `asset_id`。省略设置表示保留，显式空 `cue_bindings` 表示清空，显式 `null` 被拒绝。
- 工作空间 capabilities 的 `slideshow.audio` 决定音频资产、页面旁白和项目 cue 是否真正可用。能力未开放时，即使源码或配置写入成功，也不得向用户宣称旁白自动播放或音效已发声。
- 项目 route tree 是导航关系；页面 `project_id` 是归属关系；两者不是同一份数据。
- `suggested_components` 和项目建议资源是推荐集合，不改变组件/资源的工作空间归属，也不限制当前空间内其它可见对象。
- 页面/组件 `dependencies` 是当前版本源码真实依赖，不能用名称搜索结果替代。
- 组件草稿不是稳定公共能力；引用前查询发布版本和真实 `import_path`。
- 归档对象退出默认查询与操作边界；首版没有永久删除和 Restore。项目归档不会级联归档其页面、路由或共享资产。
- 替换资源文件会更新当前与历史页面预览；独立构建保留当次构建的资源快照。三维资源替换必须携带当前 `file_hash` 基线，页面源码中的资源 `name` 不变。
- Preview Artifact 是临时交付证据，不是项目或页面的持久化发布版本；用户要求预览或交付链接时才创建，截图仍单独作为视觉验证证据。

## 读取基线

页面创作至少要有：

1. 工作空间真实 ID、当前 Profile 和能力矩阵；
2. 目标项目详情与 `configuration`，包括画布宽高、`base_font_size`、theme/style 规范和建议组件；
3. 页面列表/目标页面详情；修改已有页面还要有最新源码和 `current_version_no`；
4. 要复用的组件、主题、样式、字体和资源的真实 ID/name、版本和使用契约；
5. 涉及路由或多页顺序时的最新 route tree。

组件创作还要有最新 `draft_hash`、`base_published_version_no`、`component_type`、源码和 `preview_schema`。

## 事实来源优先级

1. 当前 CLI 叶子命令帮助、OpenAPI Schema 和 Backend 返回的实际结果；
2. `wp standards`、`wp runtime-kit list/get`、`workspace capabilities`；
3. External API v1 文档和本 Skill references；
4. 旧截图、旧源码、对象名称和模型记忆。

冲突时重新读取当前对象和指南，不根据名称或历史文档猜测写入字段。
