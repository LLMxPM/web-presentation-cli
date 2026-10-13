# CLI 与 Agent Skill 安装指南

本指南帮助首次使用 Web Presentation 的用户完成三件事：安装 `wp` CLI、登录并选择工作空间、为当前智能体安装 `web-presentation` Skill。

## 准备条件

- Python 3.11 或更高版本；
- Web Presentation 平台账号；
- 一个已授权目标工作空间的个人访问令牌 (PAT)；
- 能执行本地终端命令并加载 `.agents/skills` 目录的智能体。

## 推荐：让智能体协助安装

把下面这段提示词复制给准备使用的智能体。它只负责安装 CLI 和 Skill；不要在 Skill 可用前让陌生智能体自行处理平台登录。

```text
请帮我安装 Web Presentation 的官方 `wp` CLI 和它内置的 `web-presentation` Skill。CLI 项目与使用说明：https://github.com/LLMxPM/web-presentation-cli 。正常安装使用 PyPI 包，不要默认克隆源码仓库。

先确认当前环境有 Python 3.11+，检查 `wp` 是否已安装；未安装时优先运行 `uv tool install web-presentation-cli`，再用 `wp --version` 验证。已安装时不要擅自升级或降级。

CLI 可用后，立即在当前项目运行 `wp skill install --scope project`；不要在安装 Skill 之前配置登录或工作空间。随后运行 `wp skill status --scope project` 验证。遇到覆盖、强制安装或降级时先停下确认。安装成功后告诉我重新加载智能体或新建会话，后续登录和工作空间配置由 `web-presentation` Skill 指引。
```

安装成功并重新加载后，可以对智能体说：

```text
请使用 $web-presentation 完成首次登录和工作空间配置。
```

Skill 会询问本地或远程 Backend，并指引你在终端隐藏输入 PAT、选择工作空间和完成环境诊断。PAT 不应出现在聊天记录里；如果你无法接管智能体的终端，请自行执行 Skill 给出的登录命令，完成后只回复“登录成功”或提供脱敏错误信息。

## 手动安装

### 1. 安装 CLI

推荐使用 `uv`：

```bash
uv tool install web-presentation-cli
wp --version
```

也可以使用 `pipx`：

```bash
pipx install web-presentation-cli
wp --version
```

如果使用 `uv` 后找不到 `wp`，运行 `uv tool update-shell`，然后重新打开终端。

### 2. 创建 PAT 并登录

登录 Web Presentation，在“账户设置” → “访问令牌 (PAT)”中创建令牌。请选择准备操作的工作空间和所需读写权限，并立即复制只展示一次的明文令牌。

本地默认服务：

```bash
wp login
```

自建或远程服务：

```bash
wp login --endpoint https://presentation.example.com
```

终端提示时再粘贴 PAT。不要为了方便把令牌写进聊天、脚本或项目文件。

### 3. 选择工作空间并诊断

```bash
wp workspace list
wp workspace use <workspace_id>
wp doctor
wp whoami
```

### 4. 安装 Skill

在目标项目内运行交互安装：

```bash
wp skill install
```

范围选择如下：

```text
1) 全局：用户目录下的 ~/.agents/skills
2) 项目：项目根目录下的 .agents/skills（默认）
```

也可使用明确的非交互命令：

```bash
# 安装到当前项目的 .agents/skills/web-presentation
wp skill install --scope project
wp skill status --scope project

# 安装到当前用户目录的 ~/.agents/skills/web-presentation
wp skill install --scope global
wp skill status --scope global
```

项目目录默认取当前 Git 根目录；不在 Git 仓库中时取当前目录，也可通过 `--project-dir PATH` 明确指定。

安装完成后重新加载智能体窗口或新建会话。CLI 不会自动修改 Agent 配置或重启 Agent。

## 安装后的第一个任务

新会话中可以这样确认 Skill 和 CLI 已被正确使用：

```text
请使用 web-presentation Skill 和 wp CLI，先以只读方式运行环境诊断，确认当前身份、默认工作空间和可用项目。不要进行任何写入，也不要展示 PAT。最后告诉我 CLI 与 Skill 是否就绪，以及我可以选择哪些项目开始创作。
```

## 更新与问题处理

升级 CLI 后需要显式同步 Skill：

```bash
uv tool upgrade web-presentation-cli
wp skill install --scope project
wp skill status --scope project
```

安装器默认不会覆盖被用户修改或未受管理的目录。只有确认需要替换时才使用 `--force`；原目录会先移动为同级备份。若旧版本曾将 Skill 安装到 `.claude/skills`、`.mimocode/skills`、`~/.config/mimocode/skills` 或 `.workbuddy/skills`，请手动删除旧目录，避免智能体优先加载过期副本。

常见检查：

```bash
wp doctor
wp profile list
wp workspace list
wp skill status --scope project
```

配置文件位于 `~/.web-presentation/config.json`，其中包含敏感 PAT。排障时不要把完整文件发送给他人，也不要提交到仓库。
