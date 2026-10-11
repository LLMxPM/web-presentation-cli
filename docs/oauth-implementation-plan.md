# CLI OAuth 实施计划

规划日期：2026-10-05。状态：计划已建立，OAuth 登录尚未实现。开发分支为本地 `oauth`，从 `master` 的 `481a586` 创建；当前 CLI 版本为 `0.3.1`。本轮只建立分支和计划，不改现有登录行为、不发布版本。

平台评估基线为 `web-presentation` 的 `mcp` 分支 `45678f3`。[主仓实施计划](https://github.com/LLMxPM/web-presentation/blob/mcp/docs/developer/cli-oauth-implementation-plan.md)负责服务端客户端规则、资源/audience、凭证、DTO、权限和平台验收；本计划负责 CLI、同步客户端、Profile、打包和 Skill。两份文档当前在本地工作树，跨仓 GitHub 链接在推送相应分支后可用。实际联测必须另行固定双方完整 commit，不能把评估基线当成支持 OAuth 的最低版本。

## 1. 首期目标与边界

交互式 `wp login` 通过系统浏览器完成平台登录与显式授权，CLI 在本机 loopback 接收授权码，用 PKCE S256 兑换面向 External API 的短期 access 与 refresh。后续命令自动管理到期和刷新，直接访问既有 `/api/v1`。

保留 PAT 用于 CI、无人值守与旧平台；认证模式显式选择，OAuth 失败不能自动转成 PAT 登录。`--no-browser` 只表示用户手动打开授权 URL，仍使用同一设备回调，不承诺支持 SSH、容器或无浏览器设备的跨设备登录。设备码流程列入后续阶段，不能用手动复制长期 Token 代替首期浏览器流程。

CLI 不持有 MCP 服务 Basic 密钥，不通过 MCP 转发业务请求，不依赖 Backend 内部包、数据库、Redis、Runtime 或 Chromium。业务路径、Scope、幂等、版本/hash 和 Job 语义仍由主仓契约约束。

## 2. 当前代码与改动位置

| 位置 | 当前行为 | 计划职责 |
| --- | --- | --- |
| `commands/auth.py` | `login` 强制输入 PAT；`logout` 只清本地；whoami 表格固定 PAT | 拆分登录编排，增加 OAuth、撤销与来源明确的身份输出 |
| `config.py` | Profile 只有 endpoint/token/default_workspace_id | 支持显式 auth 类型、兼容旧 PAT 配置，保存公共 OAuth 配置与凭据引用 |
| `wp/client.py` | 从 Profile 静态注入 token | 按当前 Profile 注入认证提供者，统一覆盖各业务命令 |
| `wp_api_client/client.py` | 同步 HTTP，每次使用同一 token，无刷新 | 通过注入的凭证提供者取得有效 access，保持同步 HTTP、幂等和轮询职责 |
| `commands/doctor.py`、`profile.py` | 诊断与列表固定 PAT | 展示认证类型、期限、授权范围和可操作错误，不显示凭据 |
| README、安装文档、Skill | 用户本人在隐藏输入中填写 PAT | 验收后引导浏览器授权，保留显式 PAT 操作和版本边界 |

OAuth HTTP 协议适配可落在 `packages/api-client/` 的独立模块；浏览器/回调、凭证存储、锁和命令编排落在 `packages/cli/`，API Client 不读 CLI 配置、不依赖 Click。具体模块名在 C1 确定，避免将全部职责放进 `auth.py` 或通用 HTTP 客户端。

## 3. 命令与契约候选

下列是目标交互，不是当前已支持的命令。服务端字段和凭证名称以主仓 P0 冻结结果为准。

| 候选命令/行为 | 目标 |
| --- | --- |
| `wp login --endpoint <平台根地址>` | 默认浏览器 OAuth；endpoint 不含 `/api/v1`，发现文档提供明确 issuer 与协议端点 |
| `wp login --no-browser` | 打印本轮授权 URL供用户本人打开；启动同设备回调并有界等待，禁止写日志或交给 Agent 代替用户批准 |
| `wp login --pat` | 用户在隐藏输入中填写 PAT；保留既有 `--token` 兼容，但文档不鼓励命令行明文传入 |
| `wp --profile <名称> login ...` | 只在目标 Profile 完成认证；失败或取消保留原有效配置 |
| `wp whoami`、`wp doctor` | 基于真实 identity/契约展示认证来源、期限、权限与空间；OAuth 关闭/不支持、需要重新登录和业务越权分别说明 |
| `wp logout` | OAuth 尝试撤销原客户端 Grant并清本地凭证；PAT 只清本地，不宣称已撤销服务端 PAT |

OAuth logout 的网络失败不阻止本地清理，但必须明确“本地已清除、远端撤销未确认”，使用约定的非零退出码，不能输出完整成功。撤销与刷新共享 Profile 锁，避免退出后迟到刷新再次保存凭据。

官方 CLI 是公开客户端，不包含共享 secret。首期候选 client_id 为 `web-presentation-cli`，resource 为平台显式 API audience，直接 access 建议使用 `wp_aat_`；这些由主仓 P0 冻结，CLI 不冒用 ChatGPT client_id，也不把 MCP `wp_oat_` 或 refresh 当成业务 Bearer。

客户端验证 HTTPS issuer、发现文档一致性和受信 endpoint；不能根据任意返回地址泄露 code/verifier/refresh。平台 origin 和授权 origin 的允许关系在 C0 固定。回调只监听 `127.0.0.1` / `::1`，使用动态空闲端口和登记路径，校验 state、iss、本轮地址、重复参数与一次性消费。S256 verifier 只在本次登录进程内保存；超时、Ctrl+C 和拒绝授权都关闭监听并清理临时状态。[原生客户端流程参考 RFC 8252](https://www.rfc-editor.org/rfc/rfc8252.html)。

## 4. 凭证保存与跨进程刷新

1. C1 确定版本化存储格式，区分 PAT 与 OAuth；保存 issuer、client_id、resource、Scope、access 到期时间及凭据引用。旧配置无 auth 类型时按现有 PAT 解释，不隐式发起浏览器登录。
2. OAuth access/refresh 使用受保护存储；C1 决定系统凭据库或独立凭据文件，并验证 Windows ACL 与 POSIX 权限。Profile 列表、JSON 输出、异常、HTTP 日志和配置备份不得暴露原始凭据。普通配置更新不覆盖其他 Profile 或正在更新的凭据。
3. 按凭据身份建立跨进程锁；多个 Profile 若共享同一刷新家族也必须共用锁。每次刷新前在锁内重读最新状态，判断是否已有其他进程完成刷新；保存新 access/refresh 与代次必须原子完成。
4. 提前刷新已知将到期的 access；长时间 Job 轮询、PNG 下载和其他业务调用都通过同一认证入口，不在各命令复制刷新逻辑。连接池、工作空间 Header 与凭据作用域保持隔离。
5. 当前主仓 refresh 是一次性轮换，旧值重放会撤销整条 Grant。刷新响应丢失或服务端提交后本地落盘失败时，不盲目重试旧 refresh；保存可识别的不确定状态，停止自动请求并提示重新登录，避免另一个进程继续使用旧值。
6. 401 不能触发无限刷新。只有明确的到期/可刷新状态才允许有界处理；403、空间越权、版本冲突、Grant 撤销和 refresh invalid_grant 不刷新。业务写入的自动重放策略在 C0 冻结，任何允许的重放都保持原幂等键、载荷和基线。
7. 锁等待、网络请求与登录都有预算；进程崩溃、锁持有者退出、logout 与刷新竞争必须可恢复或明确要求重新登录，不依靠用户手工删配置解锁。

PAT 配置和用户既有空间偏好需保留。切换认证身份后重新核对授权空间，不能继续使用已越权的默认空间。降级旧 CLI 对新配置的读取/写入兼容在 C6 用真实旧版本验证；不能预先宣称 OAuth 凭证能被旧 CLI 使用。

## 5. 分阶段工作包

| 阶段 | 工作内容 | 主仓依赖 | 完成证据 |
| --- | --- | --- | --- |
| C0 契约消费 | 固定客户端/发现/回调/resource/DTO、错误、预算与写入重放策略；记录兼容版本 | P0 | 与主仓冻结表对拍，跨仓契约正反例明确 |
| C1 配置与凭证 | 版本化 Profile、受保护存储、跨进程锁、原子更新与旧 PAT 兼容 | P0；刷新联测需 P2 | 多 Profile、共享家族、损坏配置、落盘失败、平台权限和崩溃用例通过 |
| C2 浏览器登录 | 发现、S256/state、动态 loopback、系统浏览器、拒绝/超时/取消、显式 PAT | P1/P2 | 真实授权码兑换；错误 issuer/state/回调/参数拒绝，失败保留原身份 |
| C3 请求与刷新 | 认证提供者覆盖全部 HTTP/轮询/媒体入口，轮换、撤销与不确定结果处理 | P2/P3 | 两个 CLI 进程刷新一次且凭据一致，旧 refresh 不重试；业务幂等和长任务通过 |
| C4 用户诊断 | whoami、doctor、profile、logout、结构化错误和输出脱敏 | P3 | PAT/OAuth 输出对拍，失效/关闭/越权/撤销分别有明确退出码 |
| C5 跨仓验收 | 固定双方版本、真实 CLI/TLS Gateway/Backend/Renderer/Runtime，回归 PAT/MCP | P4 | 登录→创作→轮询跨刷新→版本→预览/PNG→撤销完整证据 |
| C6 分发与 Skill | wheel/sdist、独立安装、旧版本兼容、文档与 Skill 版本、升级/回退 | P5 | Windows/Linux 实机浏览器、打包消费和公网 HTTPS 验收完成 |

按依赖推进：C0 后可进行配置和客户端开发；C2/C3 的主仓能力未就绪时可用受控 HTTP 测试推进，但必须保留“真实联调未通过”状态。C5/C6 完成后才能发布默认 OAuth 登录流程。

## 6. 验证与交付

现有回归与发行检查继续执行：

```powershell
uv sync --all-packages --frozen
uv run pytest packages/api-client/tests packages/cli/tests
uv run --project packages/cli wp --help
uv build --package web-presentation-cli --out-dir .tmp/dist
uv run python packages/cli/tests/verify_skill_distribution.py .tmp/dist
```

新增有意义的 OAuth 测试：真实进程 loopback 收码、并发刷新、轮换响应丢失、保存故障、跨 Profile/endpoint 泄露、logout 竞争、过期长轮询、写入响应丢失后的同键恢复和真实媒体下载。MockTransport 不能替代真实系统浏览器或平台认证验收；HTTP fixture 不能替代真实 PNG。

C5 联测使用专属账号、空间、数据库和回环端口，不复用用户开发数据、不重复启动开发服务。主仓负责服务端与 Gateway 断言，CLI 负责真实命令和安装包消费；跨仓契约缺失或 PG 跳过必须报告，不能作为发布通过。Windows/Linux 的浏览器、IPv4/IPv6、存储权限和文件锁分别记录支持状态；未验证的平台不声明支持。

2026-10-05 本轮评估已运行现有 API Client 与 CLI 命令定向测试，30 passed；不包含新 OAuth 行为。本轮计划只进行文档链接/围栏和 diff 检查，不将现有回归记为 OAuth 验收。

## 7. 文档、版本与发布顺序

实施落地后同步根 README、[安装指南](./getting-started.md)、[能力矩阵](./cli-capability-completion.md)、[CLI 说明](../packages/cli/README.md)、API Client 说明及 Skill 登录工作流。Skill 引导用户本人在浏览器选择权限，不读取或转发 Token，不代替用户确认；采用真实支持版本后再更新安装说明。

CLI 行为变化更新包版本；Skill 行为变化按独立版本和 `skills/catalog.toml` 维护，重新验证随包资源与兼容范围。发布前先取得已验收的平台版本和生成契约，再发布 CLI，避免安装新 CLI 后只有不可用的默认登录流程。旧平台必须给出明确的“不支持/未启用 OAuth”及显式 PAT 登录指引。

跨仓记录双方完整 commit、CLI/wheel/Skill 版本、主仓 OpenAPI 摘要、数据库/平台、测试命令与跳过项。具体服务端认证正文只由主仓维护；此计划不复制业务 Scope、DTO 或 MCP 运维。推送、标签、PyPI 发布和生产部署按后续明确的发布范围执行。

## 8. 当前进度

- [x] 从 `master` 的 `481a586` 创建并切换本地 `oauth` 分支。
- [x] 核对现有 PAT 登录、Profile、客户端与刷新缺口。
- [x] 建立 CLI 计划并关联主仓计划。
- [ ] C0 契约消费。
- [ ] C1 配置与凭证。
- [ ] C2 浏览器登录。
- [ ] C3 请求与刷新。
- [ ] C4 用户诊断。
- [ ] C5 跨仓验收。
- [ ] C6 分发与 Skill。
