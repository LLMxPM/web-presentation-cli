# CLI 公开分发

本仓库通过 PyPI 分发一个包：`web-presentation-cli`。用户安装这个包后即可获得 `wp` 命令；CLI 同步 API Client 和确定版本的官方 `web-presentation` Skill 会作为内部资源一起进入 wheel 和 source distribution，不需要单独安装。

GitHub Actions 已配置为：推送 `v*` 版本标签后，先运行 CLI/API Client 测试，再构建并发布一个 CLI 发行包。工作流文件为 `.github/workflows/publish.yml`。

## 首次配置

### 1. 创建 PyPI Trusted Publisher

登录 [PyPI](https://pypi.org/)，为 `web-presentation-cli` 添加 Pending Publisher：

| 字段 | 值 |
| --- | --- |
| Owner | `LLMxPM` |
| Repository name | `web-presentation-cli` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

首次发布前项目尚不存在时，使用 PyPI 的 Pending Publisher；首次成功发布后，它会绑定为正式 Trusted Publisher。

仓库已从 `web-presentation-agent-kit` 重命名为 `web-presentation-cli`。下次发布前必须在 PyPI 更新既有 Trusted Publisher 的 Repository name；GitHub 的旧地址重定向不会改变 PyPI 对 OIDC 仓库身份的校验，配置字段见 [PyPI 官方说明](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)。本次拆仓不发布新的 CLI 版本。

### 2. 创建 GitHub Environment

在仓库的 **Settings → Environments** 创建名为 `pypi` 的 Environment。可以为它配置 Required reviewers，让每次生产发布都需要人工批准；不需要添加 Secret，也不要把 PyPI Token 写入仓库。

## 发布一个版本

发布前只需要在 `packages/cli/pyproject.toml` 中更新 CLI 版本号，然后执行：

```bash
uv lock
uv run pytest packages/api-client/tests packages/cli/tests
git add packages/cli/pyproject.toml skills/catalog.toml uv.lock
git commit -m "发布 CLI v0.2.0"
git push origin master

git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

标签版本必须与 `packages/cli/pyproject.toml` 的 `project.version` 完全一致。推送标签后，在 GitHub **Actions → Publish Python packages** 查看构建和发布状态。

## 用户安装

面向首次使用者的 CLI 安装、PAT 安全登录、工作空间选择、Agent Skill 安装和可复制安装提示词，统一见 [CLI 与 Agent Skill 安装指南](getting-started.md)。

```bash
uv tool install web-presentation-cli
# 或
pipx install web-presentation-cli
```

安装完成后即可使用：

```bash
wp --help
wp skill install --scope global
```

CLI 和 Skill 使用独立 SemVer。构建生成的内置 manifest 记录 CLI 版本、Skill 版本、CLI 兼容范围与内容 SHA-256；升级 CLI 后使用 `wp skill status` 检查已安装副本，并重新执行 `wp skill install` 同步。安装器不在包安装或普通 CLI 启动时隐式写入 Agent 目录。

首个关联版本为 CLI `0.2.0`、Skill `1.0.0`、兼容范围 `>=0.2.0,<0.3.0`。Skill 行为发生变化时更新 `skills/catalog.toml` 中的独立版本；CLI 无关修复不要求同步提升 Skill 版本。

## 本地构建检查

正式发布前可以只构建 CLI 而不上传：

```bash
uv build --package web-presentation-cli --out-dir dist
uv run python packages/cli/tests/verify_skill_distribution.py dist
```

如果需要人工上传，使用 PyPI Token 设置 `UV_PUBLISH_TOKEN` 后执行 `uv publish`；优先使用 GitHub Actions 的 Trusted Publishing，避免长期 Token 泄露和维护成本。
