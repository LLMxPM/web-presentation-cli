"""文件功能：生成 Skill 安装诊断原因与修复指引，并完整显示长路径及命令。"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from rich.text import Text

from wp.formatter import console
from wp.skills.catalog import get_bundled_skill
from wp.skills.installer import inspect_target
from wp.skills.targets import plan_targets


STATUS_REASONS = {
    "missing": "尚未安装 Skill",
    "outdated": "已安装 Skill 落后于 CLI 内置版本或内容",
    "modified": "安装内容已修改或不完整",
    "unmanaged": "目录不是 wp 管理的安装",
    "incompatible": "已安装 Skill 与当前 CLI 不兼容",
    "newer": "已安装 Skill 版本高于当前 CLI 内置版本",
}


def _repair_command(item: dict[str, Any], skill_name: str) -> str:
    """按安装范围生成修复或检查命令；自定义内容不引导无条件覆盖。"""

    scope = item["scope"]
    install = item["status"] in {"missing", "outdated"}
    command = ["wp", "skill", "install" if install else "status", skill_name, "--scope", scope]
    if scope == "project":
        command.extend(["--project-dir", str(Path(item["path"]).parents[2])])
    return subprocess.list2cmdline(command)


def skill_diagnostic() -> dict[str, Any]:
    """检查全局和当前项目安装，返回可供终端及 JSON 共用的完整诊断。"""

    skill = get_bundled_skill("web-presentation")
    targets = [*plan_targets(skill.name, scope="global"), *plan_targets(skill.name, scope="project")]
    installed = [inspect_target(skill, target) for target in targets if target.path.exists()]
    unhealthy = [item for item in installed if item["status"] != "up_to_date"]
    if not installed:
        unhealthy = [inspect_target(skill, targets[0])]
    details = []
    for item in unhealthy:
        reason = STATUS_REASONS.get(item["status"], item["status"])
        if item.get("reason"):
            reason += f"：{item['reason']}"
        details.append({**item, "reason": reason, "action": _repair_command(item, skill.name)})
    summary = "；".join(dict.fromkeys(item["reason"] for item in details))
    return {
        "check": "Agent Skill", "status": "warning" if details else "ok",
        "value": f"{summary}；内置 v{skill.version}" if details else f"内置 v{skill.version}；已安装 {len(installed)} 处",
        "bundled_version": skill.version, "targets": details,
    }


def print_skill_details(diagnostics: list[dict[str, Any]]) -> None:
    """在表格外折行输出原因、真实版本、完整路径与操作命令，避免省略号隐藏信息。"""

    for diagnostic in diagnostics:
        if diagnostic["check"] != "Agent Skill":
            continue
        for item in diagnostic.get("targets", []):
            lines = [
                f"Skill 原因：{item['reason']}",
                f"安装版本：{item.get('installed_version', '未安装或无法识别')}；内置版本：{item['bundled_version']}",
                f"安装路径：{item['path']}",
                f"{'修复' if item['status'] in {'missing', 'outdated'} else '检查'}命令：{item['action']}",
            ]
            if item["status"] in {"modified", "unmanaged", "newer", "incompatible"}:
                lines.append("先核对安装内容与 CLI 版本；需要保留的自定义内容请先备份。")
            console.print(Text("\n".join(lines)), overflow="fold")
