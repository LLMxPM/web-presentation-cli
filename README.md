# web-presentation-cli

`web-presentation-cli` 是 `web-presentation` 的 CLI 外部 Agent 接入仓库，集中维护：

- `wp` CLI：面向 Shell/桌面 Agent 的确定性命令行能力；
- `web-presentation` Skill：指导 Agent 按工作空间、规范、校验和异步任务流程创作；
- `api-client`：供 CLI 使用的认证、工作空间上下文、幂等、错误和任务轮询客户端。

2026-10-04 起，MCP 代码、规划和服务交付独立到 [web-presentation-mcp](https://github.com/LLMxPM/web-presentation-mcp)。本仓只维护 CLI、专用同步客户端和配套 Skill；MCP 在自己的仓库维护异步客户端，两端仅共用 Backend External API 契约。远程多用户 MCP 尚未交付。拆分边界见 [仓库拆分记录](docs/repository-split.md)。

主平台仓库是 [web-presentation](https://github.com/LLMxPM/web-presentation)，项目官网与案例演示见 [https://presentation.inputloom.com/](https://presentation.inputloom.com/)。主平台负责 Backend、Editor、Runtime 和 `/api/v1` External API v1。本仓库不直接访问主平台数据库、Redis、Runtime 或 Chromium。

主仓唯一维护的 External API v1 契约：[External Agent API v1 契约](https://github.com/LLMxPM/web-presentation/blob/dev/docs/developer/reference/external-agent-api.md)。本仓库当前只维护 CLI、专用同步客户端和 Skill 的接入实现。

## 用户快速开始

### 1. 安装 CLI

需要 Python 3.11+。推荐使用 `uv`，也可以使用 `pipx`：

```bash
uv tool install web-presentation-cli
# 或
pipx install web-presentation-cli

wp --version
```

### 2. 登录并选择工作空间

先登录 Web Presentation，在“账户设置” → “访问令牌 (PAT)”中创建令牌，授权准备操作的工作空间和所需权限。然后运行：

```bash
# 本地默认服务 http://127.0.0.1:8000
wp login

# 自建或远程服务；使用 Backend 根地址，不要附加 /api/v1
wp login --endpoint https://presentation.example.com
```

CLI 会隐藏 PAT 输入。不要把令牌发送给智能体、写入项目文件或直接放进命令行参数。登录后完成工作空间选择和诊断：

```bash
wp workspace list
wp workspace use <workspace_id>
wp doctor
```

### 3. 安装 Skill

在目标项目目录执行：

```bash
wp skill install
```

交互界面中的 `2. 项目` 是推荐选项，会把 Skill 安装到项目根目录的 Agent Skill 目录；`1. 全局` 才会安装到当前用户目录。Codex、Cursor、GitHub Copilot、Gemini CLI 和 OpenCode 共用 `.agents/skills/web-presentation`，只安装一份；Claude Code 使用 `.claude/skills/web-presentation`，MiMo 使用 `.mimocode/skills/web-presentation`（全局为 `~/.config/mimocode/skills/web-presentation`），WorkBuddy 使用 `.workbuddy/skills/web-presentation`。

明确安装当前项目的全部兼容目录时，可以运行：

```bash
wp skill install --scope project --agent all
wp skill status --scope project --agent all
```

安装完成后重新加载智能体窗口或新建会话，使其重新发现 Skill。

### 4. 让智能体协助完成安装

复制下面这段即可。安装命令的选择、目录识别和排障由智能体结合当前环境与 `wp` 的交互提示完成：

```text
请帮我安装 Web Presentation 的官方 `wp` CLI 和它内置的 `web-presentation` Skill。CLI 项目与使用说明：https://github.com/LLMxPM/web-presentation-cli 。正常安装使用 PyPI 包，不要默认克隆源码仓库。

先确认当前环境有 Python 3.11+，检查 `wp` 是否已安装；未安装时优先运行 `uv tool install web-presentation-cli`，再用 `wp --version` 验证。已安装时不要擅自升级或降级。

CLI 可用后，立即在当前项目运行 `wp skill install`，选择项目级安装和当前智能体；不要在安装 Skill 之前配置登录或工作空间。随后运行 `wp skill status` 验证。遇到覆盖、强制安装或降级时先停下确认。安装成功后告诉我重新加载智能体或新建会话，后续登录和工作空间配置由 `web-presentation` Skill 指引。
```

安装成功并重新加载后，可以对智能体说：`请使用 $web-presentation 完成首次登录和工作空间配置。`

完整的手动安装步骤和问题处理见 [CLI 与 Agent Skill 安装指南](docs/getting-started.md)。

## 目录

```text
web-presentation-cli/
├── packages/
│   ├── api-client/       # CLI 专用同步 HTTP 客户端，随 CLI 打包
│   └── cli/              # wp 命令行
├── docs/                 # CLI 安装、能力和发布文档
├── skills/
│   └── web-presentation/ # 配套 Agent Skill
└── pyproject.toml        # uv workspace
```

## 本地开发

要求 Python 3.11+ 和 `uv`：

```powershell
uv sync
uv run --project packages/cli wp --help
uv run pytest
```

开发态安装 CLI：

```powershell
uv tool install --editable packages/cli
wp --help
```

安装 CLI 随包发布的 `web-presentation` Skill：

```powershell
# 缺少范围或 Agent 时，交互式终端会引导选择
wp skill install

# 非交互式安装到项目内的全部受支持 Agent
wp skill install --scope project --agent all

# 查看状态、卸载或导出标准 ZIP
wp skill status --scope project --agent all
wp skill uninstall --scope project --agent all --yes
wp skill export
```

Codex、Cursor、GitHub Copilot、Gemini CLI 和 OpenCode 共用 `.agents/skills`；Claude Code 使用 `.claude/skills`，MiMo 使用 `.mimocode/skills`（全局 `~/.config/mimocode/skills`），WorkBuddy 使用 `.workbuddy/skills`。支持项目级和当前用户全局安装，不修改 Agent 配置，也不支持任意第三方 Skill 来源。

CLI 通过本地 Profile 配置 Backend 地址、PAT 和默认工作空间。对外接口公共前缀固定为 `/api/v1`。用户安装与初始配置应优先参考上面的快速开始，不需要克隆本仓库。

2026-10-05 已在 `oauth` 开发分支建立 [CLI OAuth 实施计划](docs/oauth-implementation-plan.md)，涵盖浏览器授权、凭证保存、并发刷新和跨仓验收。当前登录仍使用 PAT，OAuth 默认登录尚未实现。

## 边界

1. Backend 是权限、工作空间隔离、业务校验和异步任务状态的最终事实源；API 语义以主仓 [External Agent API v1 契约](https://github.com/LLMxPM/web-presentation/blob/dev/docs/developer/reference/external-agent-api.md) 为准。
2. CLI 和 Skill 不复制 Backend 内部 AI `tool_specs.py`；CLI 只暴露面向用户可直接执行的资源化命令，平台契约由主仓 External API 文档维护。
3. 写操作必须携带幂等语义；页面、组件和截图等重任务通过 Backend 已有任务接口执行。
4. PAT 不得进入 CLI 输出、异常消息、日志或 telemetry。

主仓文档只维护平台契约；CLI 命令、Skill 工作流、适配测试和实施进度只在本仓维护，避免两边同时修改同一份实现说明。

## 发布关系

本期仅发布一个 CLI 包；官方 Skill 作为 CLI 发行资源一并进入 wheel 和 sdist。CLI 与 Skill 使用独立版本，并由内置 manifest 记录兼容范围和内容 SHA-256。版本发布前必须针对目标 `web-presentation` 版本运行 External API v1 契约测试。

## 公开安装与发布

公开用户可直接从 PyPI 安装 CLI：

```bash
uv tool install web-presentation-cli
# 或
pipx install web-presentation-cli
```

发布流程和 PyPI Trusted Publishing 配置见：[CLI 公开分发](docs/public-distribution.md)。

## License

当前仓库采用 Apache License 2.0，见 [LICENSE](./LICENSE)。


### 契约可用性与多页交付

CLI 0.3.0 的契约叶子帮助失败时立即非零退出，不输出部分帮助；`wp doctor` 独立检查 OpenAPI，有错误时退出 1。`--json` 输出稳定的精简业务字段，`--raw` 保留完整 Backend 响应；内置 Skill 当前为 `1.3.2`，临时文件统一约定在 `.tmp/web-presentation/`，并补充短期预览地址交付流程。CLI 0.3.1 起组件列表额外给出 `import_path` 与 `import_statement`，Skill 同步写明 `@workspace-components/<code>/v/<version_no>` 的发布版引用契约。具体安装与行为变更见 [CLI 说明](packages/cli/README.md)。
