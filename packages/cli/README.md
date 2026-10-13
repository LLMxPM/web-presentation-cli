# Web Presentation CLI (`wp`)

面向 `web-presentation` AI 演示文稿创作平台的官方命令行与 Agent 工具包。

External API 路径、Scope、错误码、幂等和异步任务语义以主仓 [External Agent API v1 契约](https://github.com/LLMxPM/web-presentation/blob/dev/docs/developer/reference/external-agent-api.md) 为准；CLI 命令和参数以本仓 `wp --help` 与 CLI 实施文档为准。

## 安装与快速开始

```bash
# 从 PyPI 安装公开发行版
uv tool install web-presentation-cli
# 或使用 pipx
pipx install web-presentation-cli

# 验证安装
wp --version
wp --help
```

需要 Python 3.11+。如果使用 `uv` 安装后终端找不到 `wp`，运行 `uv tool update-shell` 并重新打开终端。

从源码开发时才需要以下命令，普通用户不需要克隆仓库：

```bash
# 在 CLI 仓库根目录安装 CLI
uv pip install -e ./packages/cli
```

登录 Web Presentation 后，进入“账户设置” → “访问令牌 (PAT)”创建令牌，并授权准备操作的工作空间和所需权限。令牌明文只展示一次，不要发送给智能体或写入项目文件。

```bash
# 本地环境；PAT 会在终端中隐藏输入
wp login

# 自建或远程环境；Backend 根地址不要包含 /api/v1
wp login --endpoint https://presentation.example.com

# 检查环境与连通性
wp doctor

# 查看授权的工作空间并切换当前工作空间
wp workspace list
wp workspace use <workspace_id>

# 查看并切换默认 Profile（Profile 保存 Backend 地址、PAT 和默认工作空间）
wp profile list
wp profile use production
```

配置保存在当前用户的 `~/.web-presentation/config.json`。除非用于已妥善保护的无人值守环境，否则不要使用 `--token` 把 PAT 直接放入命令，以免进入 Shell 历史。

## Agent Skill 管理

CLI 内置 `web-presentation` Skill，可离线安装到 `.agents/skills` 目录。交互式终端省略参数时会引导选择全局或项目范围；脚本、管道或 JSON 模式必须显式传入 `--scope`。

```bash
# 当前用户全局安装 (~/.agents/skills/web-presentation)
wp skill install --scope global

# 当前项目安装 (<project>/.agents/skills/web-presentation)；默认解析 Git 根目录，也可用 --project-dir 指定
wp skill install --scope project

# 状态与卸载
wp skill status --scope global
wp skill uninstall --scope global --yes

# 只预览目标，或导出根目录包含 SKILL.md 的通用 ZIP
wp skill install --scope project --dry-run
wp skill export web-presentation
```

获取短期预览地址：

```bash
wp preview get --project-id <project_id>
wp preview get --project-id <project_id> --route /overview
wp preview get --page-id <page_id>
```

项目和页面目标共用同一个预览命令与 API Client 方法；页面模块入口由 Backend 解析。

JSON 输出模式：

```bash
wp --json project list
wp --raw project list
```

`--json` 输出面向 Agent 的稳定字段；`--raw` 输出 Backend 原始 JSON，二者不能同时使用。预览地址是短期 Preview Artifact 地址，不等同于正式发布地址。

首次使用建议进入智能体将要工作的项目目录，直接运行 `wp skill install`，然后选择 `2. 项目`。项目级安装会进入项目根目录下的 `.agents/skills/web-presentation`，全局安装会进入 `~/.agents/skills/web-presentation`，不是安装到 Python 包目录。安装后重新加载智能体窗口或新建会话。

Skill 与 CLI 一起发布，但使用独立版本。`wp skill status` 会识别缺失、过期、较新、不兼容、用户修改和未受管理等状态；普通升级不会覆盖用户修改，`--force` 会先保留同级备份。CLI 升级不会隐式改写已安装 Skill，需要重新运行 `wp skill install` 完成同步。若此前版本曾向 `.claude/skills`、`.mimocode/skills`、`~/.config/mimocode/skills` 或 `.workbuddy/skills` 安装过副本，升级后请手动移除这些旧目录，统一使用 `.agents/skills`。

当前版本关系：CLI `0.3.1` 内置 `web-presentation` Skill `1.3.3`，Skill 声明的 CLI 兼容范围为 `>=0.3.0,<0.4.0`。构建时会把这组关系与规范化内容 SHA-256 写入 manifest。Skill `1.3.3` 补充图片、公式、数据图表和流程图的 Runtime 组件选择，以及共享资源 name 与直接内容 content 两种使用方式。

`wp skill export` 生成的标准 ZIP 可用于支持本地上传的产品；CLI 不从 URL 或第三方仓库下载 Skill。

## 复制给智能体：安装 CLI 和 Skill

把下面这段发给当前智能体。它只负责安装 CLI 和 Skill；登录由安装后的 Skill 指引：

```text
请帮我安装 Web Presentation 的官方 `wp` CLI 和它内置的 `web-presentation` Skill。CLI 项目与使用说明：https://github.com/LLMxPM/web-presentation-cli 。正常安装使用 PyPI 包，不要默认克隆源码仓库。

先确认当前环境有 Python 3.11+，检查 `wp` 是否已安装；未安装时优先运行 `uv tool install web-presentation-cli`，再用 `wp --version` 验证。已安装时不要擅自升级或降级。

CLI 可用后，立即在当前项目运行 `wp skill install --scope project`；不要在安装 Skill 之前配置登录或工作空间。随后运行 `wp skill status --scope project` 验证。遇到覆盖、强制安装或降级时先停下确认。安装成功后告诉我重新加载智能体或新建会话，后续登录和工作空间配置由 `web-presentation` Skill 指引。
```

安装成功并重新加载后，可以对智能体说：`请使用 $web-presentation 完成首次登录和工作空间配置。`

更完整的人工操作步骤和排障说明见 [CLI 与 Agent Skill 安装指南](https://github.com/LLMxPM/web-presentation-cli/blob/master/docs/getting-started.md)。

## 常用操作

```bash
wp system health
wp project list
wp project configuration get <project_id>
wp page list --project-id <project_id>
wp page dependencies <page_id>
wp component list --scope suggested --project-id <project_id>
wp asset content get <asset_id>
wp theme list
wp style list
wp job wait <job_id>
```

复杂写入参数使用 `--payload-file`、`--edits-file`、`--content-file`、`--route-file` 和 `--ids-file`。Build、产物下载、Agent 运行、图片能力、Restore 和 MCP 不属于当前 CLI。

叶子命令的 `--help` 会从当前 Profile 的 Backend `/openapi.json` 加载请求参数和完整 Schema；契约获取或解析失败时不输出部分帮助，stderr 输出具体错误并退出 1，不缓存 Schema。

写入命令支持 `--idempotency-key <key>`；网络超时后需要重放同一业务请求时复用原 key，不要把同一个 key 用于不同请求。


### 0.3.1 行为变更

`wp component list` 表格新增「引用路径」列，未发布组件显示 `未发布`；`--json` 的组件列表与建议组件投影新增 `import_path` 与 `import_statement` 字段，取自 Backend 返回，供页面源码直接拼接 `@workspace-components/<code>/v/<version_no>` 别名。内置 Skill `1.3.2` 同步补充工作空间组件的版本化引用契约，禁止引用草稿、自增 ID 或本地相对路径。

### 0.3.0 行为变更

`--json` 现在输出面向 Agent 的稳定字段投影；`--raw` 输出完整 Backend 原始 JSON，二者不能同时使用。Project、Page、Component、Asset、Theme、Style、Validation 和 Preview 命令按场景区分列表、详情、源码和诊断字段；成功响应不再注入 `_client` 元数据。预览地址通过 `wp preview get` 获取，属于短期 Preview Artifact。

### 0.2.1 行为变更

契约叶子帮助失败立即退出 1；`--json` 错误输出在 stderr。Doctor 独立检查全部已注册 OpenAPI 契约，存在 error 时退出 1，仅 warning 仍退出 0。自动化必须检查退出码。顶层与本地配置帮助仍可离线使用。

平台须先部署 `/openapi.json` 网关修复，再升级 CLI。升级后运行 `wp skill install --help`，按原安装目标执行安装/更新，并用 `wp doctor` 确认内置和已安装 Skill 版本；多页流程、路由交付和主题示例见 Skill references。
