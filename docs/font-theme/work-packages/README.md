# CLI 字体与主题配置工作包

状态：WP06–WP08 均待实施。范围与命令候选见[本仓实施规划](../implementation-plan.md)；平台字段、Scope、错误与真值表只消费主仓 WP01 冻结结果。

| 编号 | 工作包 | 前置 | 状态 |
| --- | --- | --- | --- |
| WP06 | [字体与字体族命令](./wp06-font-commands.md) | 主仓 WP01、WP04 | 完成 |
| WP07 | [主题配置与输出](./wp07-theme-commands.md) | 主仓 WP01、WP05 | 完成 |
| WP08 | [Skill 与安装包](./wp08-skill-distribution.md) | WP06、WP07 | 待实施 |

主仓工作包入口：[联合执行清单](https://github.com/LLMxPM/web-presentation/blob/feature/cli-font-theme/docs/developer/cli-font-theme/work-packages/README.md)。跨仓 GitHub 链接推送后可用，本地位于同级主仓的同名路径。

每包对应可独立评审的提交或 PR。按“待实施 → 实施中 → 待验收 → 完成”更新；回填本仓完整 commit、主仓契约 commit/OpenAPI 摘要、已运行命令/结果、未运行项与遗留影响。主仓索引只同步状态与版本，不复制本仓命令实现正文。

WP06/WP07 完成后执行 WP08；最终由主仓 WP09 汇总真实安装包、字体加载、截图和独立构建证据。Mock、OpenAPI 对拍和真实渲染分别记录，互相不能替代。
