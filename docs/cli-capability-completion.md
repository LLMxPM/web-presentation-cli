# CLI External API v1 能力矩阵

当前 CLI 按首版本地开发契约实现，不提供旧命令、旧参数或兼容层。Backend External API 是权限、Schema、错误码和任务状态的唯一事实源。`--json` 输出稳定的 CLI 字段投影，`--raw` 保留完整 Backend 响应。

## 命令矩阵

| 资源 | CLI 命令 |
| --- | --- |
| 预览地址 | `wp preview get --project-id <id> [--route <path>]`, `wp preview get --page-id <id> [--version <version_no>]`；返回短期 `preview_url` |
| 系统 | `wp system version`, `wp system health` |
| 标准 | `wp standards page`, `wp standards component` |
| 动态请求契约 | 目标叶子命令的 `--help` 从 Backend OpenAPI 展示 |
| Runtime Kit | `wp runtime-kit list`, `wp runtime-kit get <item>` |
| 字体 | `wp font list/get/register/update`，`wp font family list/get/rename`；注册/更新使用 `--payload-file`，预设从 `workspace capabilities` 查询 |
| 项目 | `list`, `get`, `create`, `update`, `archive`, `configuration get/update`, `slideshow get/update`, `route get/add/update/replace`, `apply-style`, `build-assets update` |
| 页面 | `list`, `get`, `create`, `copy`, `update`, `source`, `edit`, `version list/get/export/diff/snapshot`, `dependencies`, `validate`, `screenshot`, `archive` |
| 组件 | `list`, `get`, `create`, `update`, `edit`, `version list/get`, `dependencies`, `validate`, `publish`, `archive` |
| 资源 | `list`, `get`, `create`, `upload`, `replace`, `download`, `update`, `copy`, `content get/update/preview`, `tags list`, `archive`；`--type` 支持 `model3d` |
| 主题 | `list`, `get`, `create`, `update`, `copy`, `archive` |
| 样式 | `list`, `get`, `create`, `update`, `copy`, `archive` |
| Mutation Job | `wp job get`, `wait`, `cancel`, `retry` |

## 文件参数

复杂参数不通过长命令行字符串拼接：

- `--payload-file`：完整 JSON 请求对象。
- `--edits-file`：源码结构化编辑数组。
- `--preview-schema-file`：Preview Schema JSON 对象。
- `--route-file`：完整项目路由树 JSON 对象。
- `--content-file`：UTF-8 原始文本内容。
- `--ids-file`：批量归档用的正整数数组。

示例：

```bash
wp --workspace 1 project configuration update 10 --payload-file .tmp/web-presentation/project-10-configuration.json
wp page edit 20 --base-version-no 3 --edits-file .tmp/web-presentation/edits-20.json
wp asset content preview 30 --content-file .tmp/web-presentation/diagram.svg
wp component update 40 --payload-file .tmp/web-presentation/component-40-metadata.json
wp page archive --ids-file .tmp/web-presentation/page-ids.json --yes
```

页面和组件创建、源码编辑、组件复杂元数据更新默认等待 Mutation Job 终态；使用 `--no-wait` 只返回 Job，再使用 `wp job wait <job_id>` 轮询。

三维资源使用 `asset upload --type model3d` 上传自包含 GLB；替换必须提供当前 `file_hash` 基线：

```bash
wp asset replace 42 .tmp/web-presentation/product-v2.glb --expected-file-hash <current_file_hash> --idempotency-key <key>
wp asset download 42 --output .tmp/web-presentation/product.glb
```

`--json asset list` 为 `model3d` 项附带 `format`、`scene_count`、`camera_count` 和 `animation_count` 摘要，完整分析元数据仍只在 `asset get` 中返回。

## 独立静态截图与 Scene 配置

CLI 0.4.1 删除任意时刻采样参数；最新/历史截图使用独立静态呈现。`page screenshot --job --no-wait` 返回任务状态，`--job-id` 可继续查询；ready 才落盘，pending/unavailable/skipped/failed 保留区别和稳定原因码，执行失败退出非零。默认最新 GET 和历史内容下载保持原语义。

放映 schema 4 只接受 manual/timer/scene_end、delay_ms、completion_delay_ms 和 loop；完成后停留允许零。旧模式、超时字段和自动开始删除。新 advance 写入前核对 schema 4，缺失声明不降级 timer。Skill 1.4.7 同步 Scene 多序列、模型 v3、显式媒体任务、cue v2 和独立静态态。

音频阶段门禁删除，严格音量/绑定参数与服务端资源、权限验证保留。真实浏览器、Mutation Job → Renderer、声音、WebGL、多窗口及独立产物由主仓 C3 验收；本仓测试与构建不代表已实测。

## 页面版本管理

页面历史以版本链保存，命令统一使用 `page_id` 与正整数 `version_no` 定位：

```bash
wp --json page version list 21 --important --limit 5
wp --json page version get 21 5
wp page version export 21 5 --output .tmp/web-presentation/page-21-v5.vue
wp page version diff 21 5 12 --field all
wp page version snapshot 21 12 --name "内容确认版" --idempotency-key page-21-v12-checkpoint
wp preview get --page-id 21 --version 5
```

- `list --important/--limit` 在 CLI 收到完整列表后先筛选再限制数量；`--json` 保持顶层数组与既有字段，不改为分页 envelope。
- `export` 与 `diff` 只使用服务端还原的 `resolved_content`；`content` 在普通历史节点上是差异文本。导出按 UTF-8 原样写入，先写同目录临时文件再原子替换，默认拒绝覆盖，`--overwrite` 才允许；`--json` 返回 `page_id`、`version_no`、`file_type`、`output_path` 与 `bytes`。
- `diff` 方向为 from → to，分别比较源码与演讲备注；无差异同样退出 0。备注 `null` 与空串语义不同，文本相同也报变更；相同版本只读取一次。
- `snapshot` 只标记已有版本，不新增版本、不切换当前版本、不改源码和备注；同版本重复提交只重命名，不同名称需要新幂等键。
- `preview get --version` 只能与 `--page-id` 搭配，与项目目标或 `--route` 混用时在发请求前报参数错误；旧 Backend 缺少历史预览路由时帮助与执行明确报不可用，不静默预览当前版本。

后端契约见主仓 External API 的 `page.version.snapshot` 与 `page.version.preview` operation；本轮不提供历史恢复命令。

## 明确不支持

当前 CLI 不提供：

- Agent Session/Run/HITL 和动态工具披露；
- 图片生成与图片识别；
- Build 任务、构建状态和产物下载；
- 永久删除和 Restore；
- MCP Server。

校验、工作空间隔离、PAT、Scope、幂等键和乐观锁均由主仓 External API 最终执行。

## B5 开发验证（2026-10-31）

对应主仓 `299708d`（配置 schema 4、Scene capability、Presenter v5 与 AI 联合样例）。本仓完整 API Client/CLI 回归 209 项通过，无跳过；版本更新后的 Skill 降级测试修正了原先恰好变为当前兼容区间的夹具。截图身份与严格版本补测在定向集合中通过；help、主仓实时生成 OpenAPI 对拍、wheel/sdist、Skill 分发与技能前置结构校验通过。

在线 uv 环境同步曾因 PyPI TLS 失败；沿用现有虚拟环境运行回归，并用 `uv build --offline` 成功构建 CLI 0.4.1、Skill 1.4.7。产物在 `.tmp/dist-0.4.1`，未发布。未访问平台业务数据库、Runtime 或 Chromium；真实创作、播放与 Renderer 链路由主仓 C3 执行。

版本号按用户要求更正为 CLI `0.4.1`、Skill `1.4.7`，兼容范围 `>=0.4.1,<0.5.0`。版本与 Skill 管理定向回归 37 项通过；离线锁文件检查、wheel/sdist 和 Skill 分发验证通过。此修正未重跑业务全量或实机测试。
