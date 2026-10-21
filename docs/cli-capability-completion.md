# CLI External API v1 能力矩阵

当前 CLI 按首版本地开发契约实现，不提供旧命令、旧参数或兼容层。Backend External API 是权限、Schema、错误码和任务状态的唯一事实源。`--json` 输出稳定的 CLI 字段投影，`--raw` 保留完整 Backend 响应。

## 命令矩阵

| 资源 | CLI 命令 |
| --- | --- |
| 预览地址 | `wp preview get --project-id <id> [--route <path>]`, `wp preview get --page-id <id>`；返回短期 `preview_url` |
| 系统 | `wp system version`, `wp system health` |
| 标准 | `wp standards page`, `wp standards component` |
| 动态请求契约 | 目标叶子命令的 `--help` 从 Backend OpenAPI 展示 |
| Runtime Kit | `wp runtime-kit list`, `wp runtime-kit get <item>` |
| 字体 | `wp font list/get/register/update`，`wp font family list/get/rename`；注册/更新使用 `--payload-file`，预设从 `workspace capabilities` 查询 |
| 项目 | `list`, `get`, `create`, `update`, `archive`, `configuration get/update`, `slideshow get/update`, `route get/add/update/replace`, `apply-style`, `build-assets update` |
| 页面 | `list`, `get`, `create`, `copy`, `update`, `source`, `edit`, `version list/get`, `dependencies`, `validate`, `screenshot`, `archive` |
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

## 指定时间轴截图

```bash
wp --json page screenshot 20 --motion-timeline-id intro --motion-label title-in --motion-offset-ms 300 \
  --motion-visual-mode reduced --target-version 4 --timeout 60 --idempotency-key page-20-motion-1 \
  --output .tmp/web-presentation/shot/page-20-intro.png
wp --json page screenshot 20 --motion-timeline-id intro --motion-at-ms 1200 --output .tmp/web-presentation/shot/page-20-1200.png
```

- `--motion-timeline-id` 必须与 `--motion-label` 或 `--motion-at-ms` 一起使用且二选一；`--motion-offset-ms` 只能搭配 `--motion-label`，`--motion-visual-mode` 为 `full | reduced`。
- 命令先读取页面和 `/workspaces/{id}/capabilities`；`timeline.enabled` 或 `timeline.capture_snapshot` 未开启时以 `TIMELINE_CAPTURE_CAPABILITY_MISSING` 退出，不创建任务，也不会退回最新默认截图。
- 成功输出 `job_id`、`screenshot_id`、`version_no` 与 `applied_motion`，下载结果写入指定文件。临时帧不更新页面默认截图指针，后续读取 latest 仍是默认海报；任务未成功时不会回退其它截图。
- 时间轴截图只证明指定时刻的静态视觉；`applied_motion` 不代表声音、动画播放或用户设备上的 reduced 效果已经验收。

## 放映时间轴能力

`project slideshow update` 与 `project route update` 在提交 `timeline_end` 或 `timeline_timeout_ms` 前按工作空间 capabilities 校验：`advance_modes` 未声明 `timeline_end` 或 schema 低于 3 时以 `SLIDESHOW_TIMELINE_CAPABILITY_MISSING` 退出，不发送写请求，也不会把未知模式静默改成 `timer`。`media_end` 与 `media_timeout_ms` 继续按 M2 能力校验。

## 明确不支持

当前 CLI 不提供：

- Agent Session/Run/HITL 和动态工具披露；
- 图片生成与图片识别；
- Build 任务、构建状态和产物下载；
- 永久删除和 Restore；
- MCP Server。

校验、工作空间隔离、PAT、Scope、幂等键和乐观锁均由主仓 External API 最终执行。
