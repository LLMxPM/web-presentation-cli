# web-presentation-cli

`web-presentation-cli` 是 `web-presentation` 的 CLI 外部 Agent 接入仓库，集中维护：

- `wp` CLI：面向 Shell/桌面 Agent 的确定性命令行能力；
- `web-presentation` Skill：指导 Agent 按工作空间、规范、校验和异步任务流程创作；
- `api-client`：供 CLI 使用的认证、工作空间上下文、幂等、错误和任务轮询客户端。

2026-10-04 起，MCP 代码、规划和服务交付独立到 [web-presentation-mcp](https://github.com/LLMxPM/web-presentation-mcp)。本仓只维护 CLI、专用同步客户端和配套 Skill；MCP 在自己的仓库维护异步客户端，两端仅共用 Backend External API 契约。远程多用户 MCP 尚未交付。拆分边界见 [仓库拆分记录](docs/repository-split.md)。

主平台仓库是 [web-presentation](https://github.com/LLMxPM/web-presentation)，项目官网与案例演示见 [https://wp.llmxpm.com/](https://wp.llmxpm.com/)。主平台负责 Backend、Editor、Runtime 和 `/api/v1` External API v1。本仓库不直接访问主平台数据库、Redis、Runtime 或 Chromium。

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

交互界面中的 `2. 项目` 是推荐选项，会把 Skill 安装到项目根目录的 `.agents/skills/web-presentation`；`1. 全局` 会安装到当前用户目录的 `~/.agents/skills/web-presentation`。

明确安装到当前项目的 `.agents/skills` 目录时，可以运行：

```bash
wp skill install --scope project
wp skill status --scope project
```

安装完成后重新加载智能体窗口或新建会话，使其重新发现 Skill。

### 4. 让智能体协助完成安装

复制下面这段即可。安装命令的选择、目录识别和排障由智能体结合当前环境与 `wp` 的交互提示完成：

```text
请帮我安装 Web Presentation 的官方 `wp` CLI 和它内置的 `web-presentation` Skill。CLI 项目与使用说明：https://github.com/LLMxPM/web-presentation-cli 。正常安装使用 PyPI 包，不要默认克隆源码仓库。

先确认当前环境有 Python 3.11+，检查 `wp` 是否已安装；未安装时优先运行 `uv tool install web-presentation-cli`，再用 `wp --version` 验证。已安装时不要擅自升级或降级。

CLI 可用后，立即在当前项目运行 `wp skill install --scope project`；不要在安装 Skill 之前配置登录或工作空间。随后运行 `wp skill status --scope project` 验证。遇到覆盖、强制安装或降级时先停下确认。安装成功后告诉我重新加载智能体或新建会话，后续登录和工作空间配置由 `web-presentation` Skill 指引。
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
# 缺少范围时，交互式终端会引导选择全局或项目
wp skill install

# 非交互式安装到项目内的 .agents/skills 目录
wp skill install --scope project

# 查看状态、卸载或导出标准 ZIP
wp skill status --scope project
wp skill uninstall --scope project --yes
wp skill export
```

Skill 统一安装到 `.agents/skills`（项目级为 `<project>/.agents/skills/web-presentation`，全局为 `~/.agents/skills/web-presentation`）。支持项目级和当前用户全局安装，不修改 Agent 配置，也不支持任意第三方 Skill 来源。

CLI 通过本地 Profile 配置 Backend 地址、PAT 和默认工作空间。对外接口公共前缀固定为 `/api/v1`。用户安装与初始配置应优先参考上面的快速开始，不需要克隆本仓库。

2026-10-05 已在 `oauth` 开发分支建立 [CLI OAuth 实施计划](docs/oauth-implementation-plan.md)，涵盖浏览器授权、凭证保存、并发刷新和跨仓验收。当前登录仍使用 PAT，OAuth 默认登录尚未实现。

2026-10-20 已在 `feature/cli-font-theme` 分支建立 [CLI 字体与主题配置实施规划](docs/font-theme/implementation-plan.md)及[工作包清单](docs/font-theme/work-packages/README.md)，覆盖字体注册/字体族命令、主题图片与字体配置、Skill 和安装包验证；当前为待实施，未改变现有命令与版本。

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

当前源码为 CLI `0.4.0`，内置 `web-presentation` Skill `1.4.6`，Skill 要求 CLI `>=0.4.0,<0.5.0`。字体与主题功能已实现并补充审查修复，真实渲染、PostgreSQL 和独立构建联合验收仍待完成，见[实施与验证记录](docs/font-theme/implementation-plan.md)。CLI 升级后需重新运行 `wp skill install --scope global` 或 `--scope project` 同步原安装位置；Doctor 会给出原因、版本、完整路径和对应修复命令。

页面和组件校验根据候选文件自动选择模式，并拒绝冲突参数；`project route add` 可将已有页面挂到顶层或已有分组，保留其它节点及放映覆盖；`route update` 仅修改已有节点。资源上传支持显式 `--overwrite`，需要版本保护或替换三维模型时使用 `asset replace --expected-file-hash`。音频资源、`project audio get/update/clear`、放映配置、历史截图与构建产物下载工作流见 [CLI 说明](packages/cli/README.md)。配置保存、截图和任务成功不能代替真实音频播放验收。
