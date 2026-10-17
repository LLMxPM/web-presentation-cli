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

`--edits-file` 的完整结构以 `wp page edit --help` 或 `wp component edit --help` 展示的当前 OpenAPI Schema 为准。所有匹配片段必须来自最新源码，并在应用时唯一命中。

页面/组件创建、源码编辑以及组件复杂 metadata 更新本身会自动校验。写入任务终态成功时，返回的 `result.validation` 字段已包含与平台智能体工具完全一致的有界布局诊断与校验文本（包含结论、摘要、布局分类统计、具体警告及定位；无警告时为 `"检查通过，无警告"`）。外部 Agent 可直接依据 `result.validation` 发现并微调布局问题，无需为了“证明已经校验”重复调用同一 `validate`；任务失败时，`error.details.validation` 亦携带错误诊断定位。

## Job 状态与处理

```bash
wp --json job get <job_id>
wp --json job wait <job_id> --timeout 120
```

终态只有 `succeeded`、`failed`、`canceled`；`pending` 和 `running` 仍在执行。`succeeded` 时检查 `result.validation` 并重新读取页面/组件；`failed`/`canceled` 必须保留 Job ID、错误码、错误消息和诊断摘要，不能把部分返回当成完成。

人工重试前确认平台明确允许 retry。网络超时或暂时性 5xx 只对安全请求有限重试；版本冲突、权限错误、参数错误、资源缺失先重新读事实并修正。重试不同业务请求不得复用幂等键。

## 视觉复核

用户要求查看可交互效果或交付链接时，获取短期预览地址：

```bash
wp --json preview get --project-id <project_id>
wp --json preview get --project-id <project_id> --route /overview
wp --json preview get --page-id <page_id>
```

`preview_url` 只用于当前 Preview Artifact 的短期访问，不代表正式发布；项目入口可通过 `--route` 指定，页面入口由 Backend 解析。预览地址用于交互检查，截图用于固定画布的视觉证据，两者不能互相替代。

成功后获取最新截图：

```bash
wp page screenshot <page_id> --output .tmp/web-presentation/shot/page-<page_id>.png
```

检查：

- 固定画布是否完整，底部或侧边是否裁切；
- 标题、正文、数字、表格是否可读，长文案是否换行失控；
- 视觉焦点、阅读顺序、主体区域垂直平衡和留白是否有意；
- 主题颜色、字体、Logo、Icon、图片、图表和三维模型是否真实加载；
- 三维模型的材质、光照、场景和相机视角是否符合预期，模型是否被容器裁切或过小；
- 空态、缺图、数据不足、错误提示和默认组件态是否仍然成立。

三维模型的动画数据不代表支持动画播放，截图只验证当前静态姿态。替换三维资源文件后，当前与历史页面预览会同步更新，独立构建保留当次资源快照；应重新截图而不是沿用替换前的视觉结论。

截图发现问题时优先对当前版本做最小结构化编辑；重新读取版本基线后再提交，不要以旧源码生成新 edits。

## 最终汇报

至少说明：

- 工作空间、项目、页面/组件的真实 ID；
- 执行的创建/编辑/配置/发布/归档动作；
- 页面或组件版本、组件发布版本、Job ID 和幂等键（如用户需要追踪）；
- 校验结果、截图路径和视觉复核结论；
- 未执行的动作、失败原因、未验证项或需要用户补充的资料。

只完成查询、候选校验或方案时，明确写“未写入”；不要用计划、预期任务或模型推断冒充平台事实。
