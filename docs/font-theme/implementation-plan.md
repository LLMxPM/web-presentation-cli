# CLI 字体管理与主题配置实施规划

规划日期：2026-10-20。状态：规划已建立，WP06–WP08 待实施。本轮只创建分支和规划，不新增命令或发布版本。

开发分支：`feature/cli-font-theme`，从 `master` / `66d793147a968cf8c2ef00f2253cfa8693a9f0d9` 创建。评估 CLI 版本 `0.3.4`、Skill `1.4.2`；主仓评估基线为 `dev` / `12d2d2564e31c6f5cd7a9c0755c5f8f54a22a5a4`。这些是分析基线，发布时另行固定已验收的版本。

平台路径、字段、Scope、错误码和业务规则只由[主仓规划](https://github.com/LLMxPM/web-presentation/blob/feature/cli-font-theme/docs/developer/cli-font-theme/implementation-plan.md)及其 WP01 冻结的 External API 契约维护。本文件负责 CLI 命令、输出、同步客户端与 Skill，不复制 Backend 模型或内部工具清单。跨仓 GitHub 链接推送后可用；本地主仓文档位于同级 `web-presentation/docs/developer/cli-font-theme/`。

## 1. 首期目标与范围

打通 CLI 的“上传字体资源 → 注册 face / 归入字体族 → 配置主题图片与字体 → 项目预览验证”流程。

- 复用现有 `asset upload --type font`、`asset download` 和带 hash 基线的 `asset replace`。
- 字体新增详情、注册、更新与字体族列表/详情/重命名；保留 `font list`。
- 主题继续使用现有创建/更新的 JSON 文件输入，允许配置 Logo、反色 Logo、项目图标和三槽字体，补齐详情输出。
- 字体预设与允许值从 Backend 契约/能力响应发现；不复制平台枚举，不猜 family_id。
- 更新 Skill 与安装包验证，明确 Backend 兼容边界和旧平台不支持错误。

不包含自动解析字体名/元数据、一次上传并注册、字体注销/停用/硬删除、新主题背景图槽位、MCP 或 OAuth。首期不增加字体解析依赖，不把原始字体文件保存到 Profile。

## 2. 当前基础与修改位置

| 位置 | 当前行为 | 本期修改 |
| --- | --- | --- |
| `commands/catalog.py` | font 只有 list，与 Runtime Kit 同文件 | 字体命令拆到独立 font 模块，保持原入口兼容 |
| `commands/asset.py` | 已接受 font，支持上传/下载/替换 | 复用传输；核对字体 MIME 与失败输出，不复制新上传流程 |
| `commands/theme.py` | 创建/更新接受 payload-file，但帮助只描述文本和色板 | 更新说明/示例，普通详情展示图片与字体来源，保持 key 不可变 |
| `output_fields.py` / `output_profiles.py` | theme JSON 已保留图片与字体字段 | 补 face/family 稳定投影、有效来源与空值可读输出 |
| `wp_api_client/client.py` | 已有 get/post/patch/upload 与字体 list | 通用传输足够则不扩展；必要字体方法保持同步与薄封装 |
| OpenAPI 帮助与 Doctor | 契约从命令注册派生，失败不回退缓存 | 新命令进入同一注册机制，禁止第二份契约清单 |
| `skills/web-presentation/` | 明确禁止主题写入 Logo、字体与族 ID | 验收后更新为基于真实查询的写入流程，维护 Skill 版本/分发清单 |

## 3. 目标命令与输入约定

下列是待实施命令。最终命令映射消费主仓 WP01/WP04/WP05 的真实契约，不能将本表作为服务端已支持的证据。

| 命令候选 | 职责与输入 |
| --- | --- |
| `wp font list` | 保留现有分页/keyword；仅按服务端支持范围扩展筛选 |
| `wp font get <font_id>` | 查询单个注册项，清晰输出 asset_id 与 family_id |
| `wp font register --payload-file <json>` | 对已有字体资源注册；输入包含真实 asset_id、family_name 与 face 配置 |
| `wp font update <font_id> --payload-file <json>` | 修改 face 配置或所属 family_name，省略字段保持原值 |
| `wp font family list` | 分页查询字体族及注册项摘要 |
| `wp font family get <family_id>` | 查询族及全部 face，取得主题绑定目标 |
| `wp font family rename <family_id> --name <name>` | 重命名；最终字段由 Backend 契约映射 |
| `wp theme create/update --payload-file <json>` | 复用现有命令输入，支持平台已开放图片/字体字段；update 保留 theme_id 参数 |
| `wp theme get <theme_id>` | 展示图片绑定、标题/正文/代码字体来源与预设；JSON/raw 行为保持兼容 |

写命令复用 `--idempotency-key`，同键重试不得修改 payload 或身份范围。复杂输入放 `.tmp/web-presentation/`，原始用户文件保持真实路径。不要在 CLI 将省略字段自动补成 null，不要用当前对象整段覆盖请求。

标准字体流程明确分两次写入：文件上传成功后保存返回的 asset_id，再注册并取得 font_id/family_id。注册失败时保留已上传资源，输出可重试步骤与真实错误；不得宣称字体已可用，也不自动删除资源。

主题图片通过真实资源 ID 绑定；字体绑定使用 family_id，不能混用 font_id 或 asset_id。清空/来源切换/默认恢复按主仓冻结真值表构造载荷。文件下载继续通过 External 资源端点，不跟随内部 asset_url 绕过公开鉴权边界。

## 4. 工作包与前置

执行记录见[工作包清单](./work-packages/README.md)。

| 编号 | 内容 | 主仓前置 | 本仓前置 |
| --- | --- | --- | --- |
| WP06 | 字体/字体族命令、输出与契约适配 | WP01 契约、WP04 字体 API | 无 |
| WP07 | 主题配置输入、详情输出与帮助 | WP01 契约、WP05 主题 API | 无 |
| WP08 | Skill、文档、版本与安装包 | 已交付契约 | WP06、WP07 |
| WP09（主仓牵头） | 真实 CLI/平台/渲染/构建联合验收 | WP02–WP05 | WP06–WP08 |

没有主仓实现时可用受控 HTTP fixture 检验命令输入，但状态只能记为实现中/待联调。真实 OpenAPI 对拍、跨仓失败和 skip 必须单列，不能提前标完成。

## 5. 验证与交付

新增测试覆盖：真实 ID 传递，文件上传与注册的阶段区别，payload 非对象/非法 null，单项/分页输出，服务端冲突，错误退出码，空值与预设来源，严格帮助/Doctor，旧 Backend 不支持新命令，以及主题省略/null 在传输中保持原义。

现有发行回归入口以本仓 AGENTS.md 为准：

```powershell
uv run pytest packages/api-client/tests packages/cli/tests
uv run --project packages/cli wp --help
uv build --package web-presentation-cli --out-dir .tmp/dist
uv run python packages/cli/tests/verify_skill_distribution.py .tmp/dist
```

首次缺依赖时再按仓库规范 `uv sync --all-packages --frozen`，不为文档规划重装环境。`test_backend_openapi_contract.py` 必须针对固定主仓版本实际运行；相邻仓缺失导致 skip 不能当成发布通过。

WP09 使用安装包执行真实上传 → 注册 → 族查询/改名 → 主题创建/更新 → 项目应用/预览/PNG → 替换/清空/默认恢复；独立构建由主仓现有平台入口负责验证，CLI 不直接启动 Runtime/Chromium。

WP08 更新根 README、CLI README、能力矩阵、设计系统与平台模型参考文档、Skill 版本/兼容范围及随包 manifest。WP09 验收前标明待发布，不修改全局安装的 CLI/Skill，不把现有版本号写成新功能已支持。

交付记录包含双方完整 commit、OpenAPI 摘要、CLI/Skill 版本、安装包摘要、测试命令/结果和 skip/未运行项。平台契约先交付，再发布依赖它的 CLI；本轮不推送、打标签或发布。

## 6. 本轮规划记录

- 已从 master 创建并切换 `feature/cli-font-theme`，遵循用户指定前缀。
- 已建立本仓 WP06–WP08 及主仓交接关系，状态均为待实施。
- 已运行：本轮 6 份新增/修改 Markdown 的只读相对链接与代码围栏检查、`git diff --check`，全部通过。主仓同批仓库检查 8 个测试文件、63 项通过，具体入口与环境限制见主仓规划记录。
- 未运行：API Client/CLI 业务测试、跨仓 OpenAPI 对拍、安装包构建/分发、真实注册/渲染/构建流程；本轮只改规划与导航，不代表新增能力验证通过。
