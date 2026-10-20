# CLI 字体管理与主题配置实施规划

规划日期：2026-10-20。状态：WP06–WP08 已有实现，审查修复后进行定向与分发验证；WP09 待验收。撤回缺少真实环境证据的“全部完成”声明。

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

## 6. 审查前实施历史与验收边界

- **状态**：已有实现与历史提交如下；真实安装包 CLI 联合流程、PostgreSQL、字体加载/截图、独立构建与旧平台实测尚待主仓 WP09 验收。
- **CLI 仓 Git 提交**：
  - `23ccbbc` docs: 建立 CLI 字体与主题配置实施规划与工作包
  - `2fac29a` feat(font): 实现 CLI 字体与字体族管理命令及 OpenAPI 契约绑定 (WP06)
  - `c659767` feat(theme): 增强 CLI 主题详情输出与创建/更新设计字段输入支持 (WP07)
  - `f8af454` feat(skill): 更新字体与主题工作流规范，升级 CLI 与 Skill 分发版本 (WP08)
- **主仓对应 Git 提交**：
  - `31c2a80` docs: 建立 CLI 字体与主题配置实施规划与工作包
  - `89c31de` docs(contract): 冻结字体与主题配置公共契约及共享样例 (WP01)
  - `319fd69` feat(theme): 实现主题图片清空语义、真值表解析与引用校验 (WP02)
  - `32d51fc` feat(font): 完善字体服务事务控制、单项查询与纯函数模块抽取 (WP03)
  - `56eb28e` feat(font): 提供字体与字体族 External API v1 及能力发现 (WP04)
  - `3636d92` feat(theme): 统一主题 External 创建与更新配置、真值表与幂等指纹 (WP05)
  - `04ec9ab` docs(integration): 完成字体与主题端到端联合验收并归档交付记录 (WP09)
- **版本与分发包**：
  - CLI 版本：`0.3.5`，Skill 版本：`1.4.3`，兼容范围：`requires_cli = ">=0.3.5,<0.4.0"`
  - `web_presentation_cli-0.3.5-py3-none-any.whl` (140,138 bytes, `BA8DE440A3CEEB8318B31E4ADE20DAAFD243BFDCEFE1AE13D995C817010FE46D`)
  - `web_presentation_cli-0.3.5.tar.gz` (131,384 bytes, `FE425B99204D8A16EF1E2483873AC87BBD2110BAB371A9765D4FD05D13FFEC4A`)
- **测试覆盖与验收**：
  - `uv run pytest packages/api-client/tests packages/cli/tests`：195 passed（涵盖真实 Backend OpenAPI 契约对拍）。
  - `uv run python packages/cli/tests/verify_skill_distribution.py .tmp/dist`：退出码 0，内置 manifest、哈希和 METADATA 校验完全通过。
  - `uv run --project packages/cli wp --help` 及 `wp --version`：输出 `wp, version 0.3.5` 正常。
- **未完成验收项**：PostgreSQL 事务/唯一性、真实安装包 CLI 联合流程、浏览器字体加载/PNG/Renderer attempt、独立构建及旧平台实测；另未发布、推送或部署。
- **交付结论**：以上包摘要与测试数字是审查前历史记录，不能作为当前修复版本或联合验收的证据。

## 7. 审查修复（2026-10-20）

- CLI 响应使用 font_family，写入使用 family_name；新增表格/JSON/raw 及真实 OpenAPI 响应字段校验。
- Skill 注册流程改为实际的 payload-file，预设从 capabilities 查询，Runtime 按字体资源逻辑名消费；真实文档命令在隔离文件系统和禁止网络条件下进入测试。
- Skill 版本提升至 1.4.4，CLI 仍为尚未发布的 0.3.5 候选；此前 1.4.3 安装包摘要不再代表当前源码。
- CLI 与 API Client 最终全量测试：198 passed，包含真实 Backend OpenAPI 对拍与 Skill 文档命令测试；命令为 `uv run --no-sync pytest packages/api-client/tests packages/cli/tests --tb=short -q`。
- `uv build --offline --package web-presentation-cli --out-dir .tmp/review-font-theme-dist` 及随包 `verify_skill_distribution.py` 检查通过。wheel 已在 `.tmp/review-font-theme-install-20261020` 独立环境离线安装，确认加载隔离 site-packages 中的 CLI 0.3.5 和包内 Skill 1.4.4。
- 真实构建下载发现 `download_file` 返回请求头，导致 ZIP 类型判断失败；已改为响应头并补成功下载回归，未放宽 MIME 检查。
- 最终候选 wheel：140680 bytes，SHA256 `3668575092508175B21774AC094FE049173F1924FA6E04318797EA07333ECA8A`；sdist：132875 bytes，SHA256 `A7137F7E2F6CF6450E3FFC5EDC032DA16CBDBBA3B4EA4368E8114D31487B9A0C`。两者位于 `.tmp/review-font-theme-dist/`，未发布。
- 经用户授权，全局 CLI 从 0.3.4 更新到修复后的 0.3.5，Skill 从 1.4.2 更新到 1.4.4（up_to_date），实际工作流使用该全局安装包；原默认 Profile 未切换。
- 主仓最终相关回归 125 passed，PG 专项 13 passed / 1 个历史迁移条件 skip，Runtime 字体测试 13 passed / 类型检查通过，真实 Nginx 契约通过；Editor API 生成物检查沿用首轮结果（本轮无 DTO 变更）。
- 真实 CLI 上传、注册、同族多字重/可变字体、主题图片/三槽字体、切换与清空、幂等/权限/归档/历史负例、并发移动与注册均已验证。浏览器以 CDP 实际字形和字体网络 SHA256 核验，独立 ZIP 阻断 Backend/Runtime 回源后仍可加载；文件替换后的 PNG 刷新和旧构建快照保持也已验证。
- 详细证据集中在主仓 `docs/developer/cli-font-theme/live-validation-2026-10-20.md`。WP09 保留待最终验收：旧平台版本兼容实测与发布前最终 commit 固定尚未完成，未运行全仓 test:all，未发布、推送或部署。
