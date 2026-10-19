# CLI 工作流

本参考只说明 `wp` 的本地上下文、文件输入和任务控制。命令参数和 payload Schema 以目标叶子命令的当前 `--help` 为准，不在 Skill 中复制。

## 首次登录与工作空间

首次配置按以下顺序完成：

1. 运行 `wp --version` 确认 CLI 可用。登录前确认用户使用本地默认 Backend，还是自建/远程 Backend。
2. 本地运行 `wp login`；远程运行 `wp login --endpoint <Backend根地址>`。Endpoint 使用 Backend 根地址，不包含 `/api/v1`。
3. 让用户本人在终端的隐藏输入中填写 PAT。不要要求用户把 PAT 发到聊天中，不读取、打印或复述配置文件中的 Token；如果用户无法接管当前终端，只提供登录命令并等待用户完成。
4. 登录后运行 `wp workspace list`。只有一个授权工作空间时可直接设为默认值；存在多个时展示非敏感的名称和 ID，让用户选择后再运行 `wp workspace use <workspace_id>`，不要代替用户猜测。
5. 运行 `wp whoami` 和 `wp doctor`，确认身份、Backend、默认工作空间和权限均可用，再开始平台对象任务。

常用命令：

```bash
wp login
wp whoami
wp doctor
wp profile list
wp profile use <profile>
wp workspace list
wp workspace use <workspace_id>
```

## Profile 与请求上下文

需要访问多个 Backend 或身份时，用 Profile 隔离配置；先查看列表，再明确切换目标 Profile。不要读取或展示 Profile 配置中的 PAT。

全局选项必须放在子命令之前：

```bash
wp --profile production --workspace <workspace_id> --json project list
```

`--workspace` 只设置请求上下文，不替代 Backend 权限和对象归属校验。没有明确唯一工作空间时不写入。

## Help 与输出

复杂命令先读取完整叶子帮助：

```bash
wp page create --help
wp component update --help
```

依赖契约的叶子帮助必须成功读取并解析 `/openapi.json`，才会输出调用语法与完整请求契约。失败时不输出部分帮助，stderr 报告错误码、URL、HTTP 状态、Content-Type 和失败位置，退出码为 1；`--json` 输出结构化错误。顶层、命令组和本地配置帮助不依赖契约。

契约失败先运行 `wp doctor`，区分健康、契约和认证结果；任一 error 使 doctor 退出 1。HTML 响应应检查网关是否返回前端入口，路径/方法/引用缺失应检查服务端与 CLI 契约。修复后重新读取帮助，不猜字段、不以试探写入寻找 Schema，也不读取内部源码绕过公开契约。没有缓存、离线 Schema 或自动重试。

`--json` 用于稳定解析面向 Agent 的精简业务字段，复杂响应默认已经是 JSON。`--raw` 输出 Backend 原始 JSON，并自动启用 JSON 输出；二者不能同时使用。不要解析 Rich 表格文案来获取 ID、版本或状态。

## 获取短期预览地址

用户要求查看效果、交付链接或最终汇报时，先确认目标对象已成功写入并重新读取最新版本，再按目标调用：

```bash
wp --json preview get --project-id <project_id>
wp --json preview get --project-id <project_id> --route overview
wp --json preview get --page-id <page_id>
```

项目预览支持 `--route`，页面预览不支持 `--route`；项目和页面目标只能选择一种。响应中的 `preview_url` 是短期 Preview Artifact 地址，不是正式发布地址。Windows Git Bash 会把 `/overview` 当作文件路径转换；优先使用不带前导斜杠的 `--route overview`，确需前导斜杠时使用 `MSYS_NO_PATHCONV=1`。

## 音频资源与项目音频设置

先读取能力：

```bash
wp --json workspace capabilities --workspace-id <workspace_id>
```

`slideshow.audio` 的 `audio_assets`、`page_narration`、`audio_cues` 分别表示音频资产、页面旁白和项目 cue 是否开放。未开放的能力不得写入或向用户承诺；当前服务可能只开放 `audio_assets`。

音频是 `asset_type=audio` 的工作空间资源：

```bash
wp --json asset list
wp --json asset get <asset_id>
wp asset upload .tmp/web-presentation/chapter-01.mp3 --type audio --name chapter-01 --idempotency-key <key>
wp asset download <asset_id> --output .tmp/web-presentation/chapter-01.mp3
wp asset replace <asset_id> .tmp/web-presentation/chapter-01-v2.mp3 \
  --expected-file-hash <current_file_hash> --idempotency-key <key>
```

当前 CLI 的 `--type` 若不包含 `audio`，停止并报告需要升级 CLI，不要改用其他资源类型或直接调用未公开接口。替换前从 `asset get` 读取最新 `file_hash`；`ASSET_VERSION_CONFLICT` 表示基线过期，重新读取后再提交。

项目音频设置使用专用命令，不要把读取模型直接写回：

```bash
wp --json project audio get <project_id>
wp --json project audio update <project_id> --audio-file .tmp/web-presentation/project-audio.json --idempotency-key <key>
wp --json project audio clear <project_id> --idempotency-key <key>
```

- `get` 返回带 `asset_name`、`asset_type`、`asset_status` 的读取摘要；`update` 只接受 `master_volume_percent`、`narration_volume_percent`、`effects_volume_percent` 与 `cue_bindings`（每项只允许 `key`、`asset_id`、`gain_percent`）。
- `update` 必须提交完整对象，未知字段、只读字段、`null` 与缺失音量会被拒绝；显式空 `cue_bindings` 表示清空绑定。
- `clear` 只删除 cue 绑定并保留三段音量，由服务端单事务执行；不要用 `get` 后 `update` 模拟清空。
- cue 绑定只接受当前工作空间 active 音频资源的 ID，key 为小写点分段且在同一项目内唯一。含非空 cue 的写入（含 `project update` 与 `project configuration update`）要求 `capabilities.slideshow.audio.audio_cues=true`；能力缺失或为 false 时 CLI 不发送写入。
- `wp project get --json` 保留服务端返回的 `slideshow` 与 `audio_settings`；旧服务端缺字段时保持缺失，不补 null 或默认配置。需要完整绑定摘要时仍使用 `project audio get` 或 `project configuration get`。

旁白与交互音效的页面写法、能力约束和验证边界见 [资源与设计系统](./design-system-and-assets.md)；CLI 只能写入配置和源码，不能证明声音已播放。

## 临时文件目录

本地 JSON、Vue SFC 和截图只是 CLI 的输入输出载体，不是平台内容的事实源。统一写在当前会话工作目录下，不要写入 Skill 安装目录、Python 包目录或其它系统路径：

```text
.tmp/web-presentation/
.tmp/web-presentation/shot/
```

约定：

- 输入载体（payload、edits、候选/写出的 SFC、route tree、资源文本与元数据、待上传音频/模型）写在 `.tmp/web-presentation/` 下；文件名尽量带对象类型与 ID，例如 `page-42.vue`、`edits-42.json`、`component-7.vue`、`route-tree.json`、`product.glb`、`chapter-01.mp3`；
- 截图等输出证据写在 `.tmp/web-presentation/shot/`，例如 `shot/page-42.png`；下载的原始资源文件写入 `.tmp/web-presentation/`，不要写回 Skill 或包目录；
- 用户提供的原始素材保持其真实路径；智能体自行生成或落盘的中间文件一律进入上述目录；
- 汇报时给出相对路径即可；这些文件可随时删除，交付事实以 Backend 对象、Job 终态和重新读取结果为准。

## 文件参数

复杂 JSON、Vue SFC 和资源内容通过文件传入，不在 Shell 中拼接长文本。常见入口包括：

- `--payload-file`：完整 JSON 请求体；
- `--edits-file`：结构化编辑 JSON 数组；
- `--preview-schema-file`：组件预览 Schema JSON 对象；
- `--content-file`：完整 UTF-8 文本；
- `--route-file`：完整路由树 JSON；
- `--edit-file`：路由编辑 JSON 数组，用于排序、隐藏与逐页放映覆盖；
- `--slideshow-file`：完整项目默认放映配置；
- `--ids-file`：只含正整数的 JSON 数组。

具体根节点、字段、枚举和参数组合只以对应命令 `--help` 中的当前 OpenAPI Schema 为准。示例路径默认相对于 `.tmp/web-presentation/`。

## 写入、幂等与任务

所有写入、取消和人工重试命令都使用业务级 `--idempotency-key`。网络超时后，只有重放同一业务请求时复用原 key；不同请求不得复用。

页面/组件重任务默认等待。使用 `--no-wait` 时保存返回的 Job ID，再查询或等待：

```bash
wp --json job get <job_id>
wp --json job wait <job_id> --timeout 120
```

`pending`、`running` 不是完成；只有 `succeeded` 表示成功。`failed` 或 `canceled` 必须按错误码、版本基线和诊断处理。仅当平台明确标记任务可人工重试时使用 `wp job retry`。

归档默认保留交互确认。只有用户已明确授权当前归档目标时才使用 `--yes`；批量目标先核对 `--ids-file` 中的完整 ID 集合。
