# 校验与交付

页面和组件写入由 Backend 的 Mutation Job 负责编译、渲染和布局检查。外部 Agent 的职责是提交正确基线、等待终态、重新读取最新对象；用户要求交付链接时获取短期预览地址，并用截图验证真实视觉。

## 候选校验和写入校验

独立校验适用于：写入前检查一份候选 SFC、结构化 edits，或失败后请求详细诊断：

```bash
wp --json page validate <page_id> --mode content --source-file .tmp/web-presentation/page-<page_id>.vue --detail
wp --json page validate <page_id> --mode edits --edits-file .tmp/web-presentation/edits-<page_id>.json --detail
wp --json component validate <component_id> --mode content --source-file .tmp/web-presentation/component-<component_id>.vue --detail
```

`current` 检查当前内容，`content` 检查完整候选源码，`edits` 检查基于当前对象的结构化编辑；具体参数以命令帮助为准。校验不通过是诊断结果，不是写入成功。

CLI 0.3.4 起省略 `--mode` 时，`--source-file` 自动选择 `content`，`--edits-file` 自动选择 `edits`，无文件才使用 `current`。两种文件不能同时提供；显式模式与文件不匹配、候选 edits 为空时直接报错，不发送校验请求。返回的 `mode` 应与实际输入一致，候选源码使用 `content`，不是 `candidate`。

`--edits-file` 的完整结构以 `wp page edit --help` 或 `wp component edit --help` 展示的当前 OpenAPI Schema 为准。所有匹配片段必须来自最新源码，并在应用时唯一命中。

页面/组件创建、源码编辑以及组件复杂 metadata 更新本身会自动校验。写入任务终态成功时，返回的 `result.validation` 字段已包含与平台智能体工具完全一致的有界布局诊断与校验文本（包含结论、摘要、布局分类统计、具体警告及定位；无警告时为 `"检查通过，无警告"`）。外部 Agent 可直接依据 `result.validation` 发现并微调布局问题，无需为了“证明已经校验”重复调用同一 `validate`；任务失败时，`error.details.validation` 亦携带错误诊断定位。

## Job 状态与处理

```bash
wp --json job get <job_id>
wp --json job wait <job_id> --timeout 120
```

终态只有 `succeeded`、`failed`、`canceled`；`pending` 和 `running` 仍在执行。`succeeded` 时检查 `result.validation` 并重新读取页面/组件；`failed`/`canceled` 必须保留 Job ID、错误码、错误消息和诊断摘要，不能把部分返回当成完成。

人工重试前确认平台明确允许 retry。网络超时或暂时性 5xx 只对安全请求有限重试；版本冲突、权限错误、参数错误、资源缺失先重新读事实并修正。重试不同业务请求不得复用幂等键。

`RENDER_SERVICE_UNAVAILABLE` 表示页面视觉诊断执行不可用，不能把失败当成“代码已通过”。不要在外部 Agent 中伪造校验结果或绕过平台写入校验；先确认 Renderer 与 Backend 的运行态，恢复后重试，仍不可用则把视觉校验列为未完成项。

## 视觉复核

用户要求查看可交互效果或交付链接时，获取短期预览地址：

```bash
wp --json preview get --project-id <project_id>
wp --json preview get --project-id <project_id> --route overview
wp --json preview get --page-id <page_id>
```

`preview_url` 只用于当前 Preview Artifact 的短期访问，不代表正式发布；项目入口可通过 `--route` 指定，页面入口由 Backend 解析。Windows Git Bash 会把 `/overview` 当作文件路径转换；优先使用不带前导斜杠的 `--route overview`，确需前导斜杠时使用 `MSYS_NO_PATHCONV=1`。预览地址用于交互检查，截图用于固定画布的视觉证据，两者不能互相替代。

成功后获取最新截图：

```bash
wp page screenshot <page_id> --output .tmp/web-presentation/shot/page-<page_id>.png
wp --json page screenshot <page_id> --screenshot-id <content_hash> --output .tmp/web-presentation/shot/history.png
```

`--screenshot-id` 只按页面范围内的内容 ID 下载已有截图，不刷新页面、不触发 `preview:run`；内容不存在时保留 404，不回退最新截图。历史内容接口不返回页面版本，输出中的 `version_no` 为 `null`，文件名也不要使用当前页面版本。

需要固定页面中的某一时间轴状态时，使用异步时间轴截图：

```bash
wp --json page screenshot <page_id> --motion-timeline-id <timeline_id> \
  --motion-label <at_label> [--motion-offset-ms <ms>] [--motion-visual-mode full|reduced] \
  --target-version <version_no> --timeout 60 --idempotency-key <key> \
  --output .tmp/web-presentation/shot/page-<page_id>-<label>.png
wp --json page screenshot <page_id> --motion-timeline-id <timeline_id> --motion-at-ms <ms>
```

`--motion-label` 与 `--motion-at-ms` 必须二选一，`--motion-offset-ms` 只能搭配 label；时间轴 ID 必须来自页面实际声明的定义，不要猜测名称。命令先校验工作空间 `timeline.enabled` 与 `timeline.capture_snapshot`，能力未开启时返回 `TIMELINE_CAPTURE_CAPABILITY_MISSING` 且不创建任务；不要改用 latest 截图冒充指定状态。成功结果包含 `job_id`、`screenshot_id`、`version_no` 和 `applied_motion`，临时帧不会更新页面默认截图。`applied_motion` 只说明采样状态，静态帧不能证明声音已播放、动画在用户设备上流畅或 reduced 模式符合预期；这些仍需在真实预览或放映中人工观察。

构建产物下载只适用于已知 `build_job_id` 的任务：

```bash
wp --json project build artifact <project_id> <build_job_id> --output .tmp/web-presentation/build.zip
```

CLI 不能发起或查询构建任务；输出中的 `local_sha256` 只用于校验落盘内容，不是服务端可信摘要。

检查：

- 固定画布是否完整，底部或侧边是否裁切；
- 标题、正文、数字、表格是否可读，长文案是否换行失控；
- 视觉焦点、阅读顺序、主体区域垂直平衡和留白是否有意；
- 主题颜色、字体、Logo、Icon、图片、音频、图表和三维模型是否真实加载；
- 三维模型的材质、光照、场景和相机视角是否符合预期，模型是否被容器裁切或过小；
- 音频播放器是否有明确、可读的容器和控件，是否被裁切或与其它内容重叠；
- 空态、缺图、数据不足、错误提示和默认组件态是否仍然成立。

三维模型的动画数据不代表支持动画播放，截图只验证当前静态姿态。替换三维资源文件后，当前与历史页面预览会同步更新，独立构建保留当次资源快照；应重新截图而不是沿用替换前的视觉结论。音频同理，截图不能证明声音已播放、旁白已自动启动或 cue 已发声；这些行为必须在用户手动操作的预览或放映中验证，并且遵守 `slideshow.audio` 能力开关。音频替换后重新截图确认播放器与布局，不要声称已完成听觉验收。

页内时间轴同理：默认海报和指定时刻截图都只是静态证据，不能代替播放、暂停、定位与重播验收。修改放映配置时，`timeline_end` 仅在 capabilities 的 `advance_modes` 声明且 schema >= 3 时可用，`timeline_timeout_ms` 属于播放预算；能力缺失会以 `SLIDESHOW_TIMELINE_CAPABILITY_MISSING` 拒绝写入，不要自行降级为 `timer`。

截图发现问题时优先对当前版本做最小结构化编辑；重新读取版本基线后再提交，不要以旧源码生成新 edits。

## 最终汇报

至少说明：

- 工作空间、项目、页面/组件的真实 ID；
- 执行的创建/编辑/配置/发布/归档动作；
- 页面或组件版本、组件发布版本、Job ID 和幂等键（如用户需要追踪）；
- 校验结果、截图路径和视觉复核结论；
- 未执行的动作、失败原因、未验证项或需要用户补充的资料。

只完成查询、候选校验或方案时，明确写“未写入”；不要用计划、预期任务或模型推断冒充平台事实。
