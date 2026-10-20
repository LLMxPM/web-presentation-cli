# WP08：Skill、文档、兼容版本与安装包交付

状态：已实现，真实环境兼容与联合验收待补齐。主责：CLI / Skill / 分发。前置：[WP06](./wp06-font-commands.md)、[WP07](./wp07-theme-commands.md)。历史包记录见下，本轮修复版本与验证见[本仓规划](../implementation-plan.md)。

## 修改范围与任务

- 更新根 README、packages/cli/README、能力矩阵及必要安装说明，明确新命令的最低平台/CLI 支持版本与未发布状态。
- 更新 Skill 的平台导览、资源设计系统、平台模型与 CLI 工作流：上传不等于注册，三类 ID 不混用，先查字体族和预设，再配置主题。
- 替换目前“不要写入 Logo、字体、字体族 ID”的规则，改为仅使用真实查询结果和已开放字段；内部助手与 External CLI 权限分别说明。
- 增加真实命令流程示例、清空/默认恢复、注册失败后的资源保留与重试提示；临时 payload 路径保持 `.tmp/web-presentation/`。
- 不改变固定画布、Runtime Kit 版本、资源权限和归档边界；不宣传尚未实现的自动字体推断/硬删除能力。
- CLI/Skill 行为变更按独立版本管理，更新 skills/catalog.toml、兼容范围和随包资源摘要；规划时的旧版本不能被写成已支持。
- 构建 wheel/sdist，验证内嵌 Skill、独立安装、命令帮助、导出/安装/状态检查；不覆盖用户全局 CLI 或 Skill。

## 验收标准

- [x] 文档与 Skill 中不存在“已开放字段禁止使用”和“未实现能力已支持”的冲突。
- [x] 示例只使用真实公开命令和查询得到的 ID/预设，复杂输入与失败恢复步骤可执行。
- [x] CLI/Skill 版本、兼容范围、manifest/哈希和安装包资源一致。
- [x] 客户端/CLI 全量测试、真实 OpenAPI 对拍和 Skill 分发验证通过，skip 单列。
- [ ] wheel/sdist 安装消费和旧平台兼容均有实测证据；本轮可验证安装包结构与隔离安装，旧平台仍待验收。
- [ ] WP09 已完成真实联合验收并固定最终版本；此前保持待发布状态。

## 验证与记录

以下为审查前历史记录，Skill 已修正为 1.4.4，旧产物哈希不代表修复后的源码。API/Mock 测试与分发检查不能证明 WP09 的字体加载、截图或独立构建已通过。

- **发布版本更新**：
  - CLI 版本：`0.3.5`（`packages/cli/pyproject.toml`, `packages/cli/src/wp/__init__.py`）
  - Skill 版本：`1.4.3`（`skills/catalog.toml`）
  - 兼容要求：`requires_cli = ">=0.3.5,<0.4.0"`
- **构建包生成与哈希验证**：
  - `web_presentation_cli-0.3.5-py3-none-any.whl` (140,138 bytes, SHA256: `BA8DE440A3CEEB8318B31E4ADE20DAAFD243BFDCEFE1AE13D995C817010FE46D`)
  - `web_presentation_cli-0.3.5.tar.gz` (131,384 bytes, SHA256: `FE425B99204D8A16EF1E2483873AC87BBD2110BAB371A9765D4FD05D13FFEC4A`)
- **验证命令与结果**：
  - `uv run pytest packages/api-client/tests packages/cli/tests`：195 passed (包含真实 OpenAPI 契约对拍)。
  - `uv build --package web-presentation-cli --out-dir .tmp/dist`：构建成功。
  - `uv run python packages/cli/tests/verify_skill_distribution.py .tmp/dist`：通过（内容清单、规范化哈希与 METADATA 一致）。
  - `uv run --project packages/cli wp --help` 及 `wp --version`：输出 `wp, version 0.3.5` 正常。
