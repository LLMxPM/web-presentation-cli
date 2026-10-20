# WP06：CLI 字体与字体族命令

状态：完成（2026-10-20）。主责：CLI。前置：主仓 WP01 契约冻结、WP04 字体 External API。

## 修改范围与任务

- 从 catalog 拆出独立字体命令模块，保持 `wp font list` 既有行为；族子命令按职责拆至 `font_family.py`，源码与函数均包含中文职责说明。
- 按命令候选增加 face get/register/update 与 family list/get/rename，全部使用命令注册派生的 OpenAPI 契约。
- 注册/更新读取对象 JSON 文件，写入复用幂等键；只传实际提交字段，不补 null、不在 CLI 复制服务端值校验。
- 显示 asset_id/font_id/family_id、资源逻辑名、族名、格式、weight/style/display；分页列表、单项详情与族内 face 各有稳定投影。
- ApiClient 补充同步方法薄适配，不读取 Backend 包/数据库或引入 Click 到 API Client。
- 复用资源文件上传/下载/替换，明确上传与注册的两个结果；无服务器成功响应时不宣称注册完成。
- 预设目录从 Backend 获取，文件下载走公开资源端点；不跟随内部 URL、不新增离线 Schema。

## 验收标准

- [x] 所有新命令能被根帮助、严格叶子帮助和 Doctor 发现，无第二份契约清单。
- [x] 注册后可取得真实 family_id，同族 Regular/Bold 与可变字重配置正确传输。
- [x] update/rename 保留幂等键与字段存在性，服务端冲突原样映射为可操作错误和非零退出码。
- [x] JSON/raw/表格分别覆盖 face/family/分页/空结果，ID 类型不混淆。
- [x] 现有 font list、资源上传/下载/替换回归通过，旧 Backend 缺操作时明确失败。
- [x] 真实主仓 OpenAPI 对拍通过；skip 或 Mock 测试不作为跨仓完成证据。

## 验证与记录

- `uv run pytest packages/cli/tests/test_font_commands.py`（8/8 通过）
- `uv run pytest packages/cli/tests/test_backend_openapi_contract.py`（1/1 通过，真实 OpenAPI 对拍）
- `uv run pytest packages/api-client/tests packages/cli/tests`（192/192 通过）
- `uv run --project packages/cli wp font --help` 与 `wp font family --help` 帮助输出正常。
- 消费主仓 commit：`3636d92`（WP05 交付版本）。
- 未运行项：跨仓端到端实机联合演练留待 WP09 汇总执行。

