"""文件功能：解析 Agent Skill 的全局与项目级 .agents/skills 安装目标。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class SkillTarget:
    """表示一个实际写入的 .agents/skills 目录目标及其安装范围。"""

    path: Path
    base: Path
    scope: str


def resolve_project_root(project_dir: Path | None = None) -> Path:
    """解析项目根目录；显式目录优先，否则使用 Git 根并回退当前目录。"""

    if project_dir is not None:
        return project_dir.expanduser().resolve()
    current = Path.cwd().resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=current,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.SubprocessError):
        return current


def plan_targets(
    skill_name: str,
    *,
    scope: str,
    project_dir: Path | None = None,
    home_dir: Path | None = None,
) -> list[SkillTarget]:
    """为指定安装范围生成统一的 .agents/skills 安装目标。"""

    if scope not in {"global", "project"}:
        raise ValueError(f"不支持的安装范围: {scope}")
    base = (
        (home_dir or Path.home()).expanduser().resolve()
        if scope == "global"
        else resolve_project_root(project_dir)
    )
    root = base / ".agents" / "skills"
    return [SkillTarget(path=root / skill_name, base=base, scope=scope)]
