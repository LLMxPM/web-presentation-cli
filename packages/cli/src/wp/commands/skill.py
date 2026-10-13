"""文件功能：提供内置 Agent Skill 的安装、状态、卸载与 ZIP 导出命令。"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable

import click

from wp.formatter import print_json, print_success, print_table
from wp.skills.catalog import get_bundled_skill
from wp.skills.installer import (
    SkillInstallError,
    export_skill,
    inspect_target,
    install_skill,
    uninstall_skill,
)
from wp.skills.targets import plan_targets


def _common_target_options(command: Callable[..., Any]) -> Callable[..., Any]:
    """为安装、状态和卸载命令注册一致的范围与项目目录参数。"""

    options = [
        click.option("--json", "skill_json", is_flag=True, help="以 JSON 输出当前命令结果。"),
        click.option(
            "--project-dir",
            type=click.Path(path_type=Path, file_okay=False, exists=True, resolve_path=True),
            help="项目级安装根目录；默认使用当前 Git 仓库根目录。",
        ),
        click.option("--scope", type=click.Choice(("global", "project")), help="安装范围。"),
    ]
    for option in reversed(options):
        command = option(command)
    return command


def _resolve_scope(
    ctx: click.Context,
    scope: str | None,
    *,
    skill_json: bool,
    operation: str,
) -> str:
    """解析显式或交互范围选择；JSON/非 TTY 场景禁止等待输入。"""

    if scope is not None:
        return scope
    as_json = skill_json or bool(ctx.obj.get("as_json"))
    interactive = sys.stdin.isatty() and not as_json
    if not interactive:
        raise click.UsageError("缺少 --scope；非交互或 JSON 模式必须显式指定 global 或 project。")
    operation_labels = {
        "install": "安装",
        "status": "检查",
        "uninstall": "卸载",
    }
    scope_action = operation_labels[operation]
    click.echo(f"请选择{scope_action}范围：")
    click.echo("  1) 全局：用户目录下的 ~/.agents/skills")
    click.echo("  2) 项目：项目根目录下的 .agents/skills")
    scope_choice = click.prompt(
        "请输入范围编号",
        type=click.Choice(("1", "2")),
        default="2",
    )
    return {"1": "global", "2": "project"}[scope_choice]


def _load_targets(
    ctx: click.Context,
    skill_name: str,
    scope: str | None,
    project_dir: Path | None,
    skill_json: bool,
    operation: str,
) -> tuple[Any, list[Any], bool]:
    """加载内置 Skill 和对应范围的 .agents/skills 目标，并统一转换参数错误。"""

    try:
        skill = get_bundled_skill(skill_name)
        resolved_scope = _resolve_scope(
            ctx,
            scope,
            skill_json=skill_json,
            operation=operation,
        )
        targets = plan_targets(
            skill_name,
            scope=resolved_scope,
            project_dir=project_dir,
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    return skill, targets, skill_json or bool(ctx.obj.get("as_json"))


def _output_targets(title: str, results: list[dict[str, Any]], *, as_json: bool) -> None:
    """输出目标操作结果，JSON 模式保留全部诊断字段。"""

    if as_json:
        print_json({"targets": results})
        return
    rows = [
        [
            item.get("scope", ""),
            item.get("status", ""),
            item.get("action", "-"),
            item.get("path", ""),
        ]
        for item in results
    ]
    print_table(title, ["范围", "状态", "操作", "路径"], rows)


@click.group("skill")
def skill_group() -> None:
    """安装和管理随 wp CLI 发布的 Agent Skill。"""


@skill_group.command("install")
@click.argument("skill_name", default="web-presentation")
@_common_target_options
@click.option("--dry-run", is_flag=True, help="仅显示计划，不写入文件。")
@click.option("--force", is_flag=True, help="备份后覆盖未受管理或已修改的目标。")
@click.option("--yes", is_flag=True, help="跳过强制覆盖确认。")
@click.option("--allow-downgrade", is_flag=True, help="允许安装低于当前已安装版本的内置 Skill。")
@click.pass_context
def skill_install_cmd(
    ctx: click.Context,
    skill_name: str,
    scope: str | None,
    project_dir: Path | None,
    skill_json: bool,
    dry_run: bool,
    force: bool,
    yes: bool,
    allow_downgrade: bool,
) -> None:
    """把 CLI 内置 Skill 安装到全局或项目级 .agents/skills 目录。"""

    skill, targets, as_json = _load_targets(
        ctx, skill_name, scope, project_dir, skill_json, "install"
    )
    if force and not dry_run and not yes:
        if as_json or not sys.stdin.isatty():
            raise click.UsageError("非交互或 JSON 模式使用 --force 时必须同时提供 --yes。")
        click.confirm("强制安装会备份并替换冲突目录，是否继续？", abort=True)
    try:
        results = [
            install_skill(
                skill,
                target,
                dry_run=dry_run,
                force=force,
                allow_downgrade=allow_downgrade,
            )
            for target in targets
        ]
    except (OSError, SkillInstallError) as exc:
        raise click.ClickException(str(exc)) from exc
    _output_targets("Skill 安装结果", results, as_json=as_json)


@skill_group.command("status")
@click.argument("skill_name", default="web-presentation")
@_common_target_options
@click.pass_context
def skill_status_cmd(
    ctx: click.Context,
    skill_name: str,
    scope: str | None,
    project_dir: Path | None,
    skill_json: bool,
) -> None:
    """检查目标 Skill 的安装、版本、兼容性和用户修改状态。"""

    skill, targets, as_json = _load_targets(
        ctx, skill_name, scope, project_dir, skill_json, "status"
    )
    try:
        results = [inspect_target(skill, target) for target in targets]
    except (OSError, SkillInstallError) as exc:
        raise click.ClickException(str(exc)) from exc
    _output_targets("Skill 状态", results, as_json=as_json)


@skill_group.command("uninstall")
@click.argument("skill_name", default="web-presentation")
@_common_target_options
@click.option("--force", is_flag=True, help="备份并移除未受管理或已修改的目标。")
@click.option("--yes", is_flag=True, help="跳过卸载确认。")
@click.pass_context
def skill_uninstall_cmd(
    ctx: click.Context,
    skill_name: str,
    scope: str | None,
    project_dir: Path | None,
    skill_json: bool,
    force: bool,
    yes: bool,
) -> None:
    """卸载由 wp 管理的 Skill，异常目标在强制模式下保留备份。"""

    skill, targets, as_json = _load_targets(
        ctx, skill_name, scope, project_dir, skill_json, "uninstall"
    )
    if not yes:
        if as_json or not sys.stdin.isatty():
            raise click.UsageError("非交互或 JSON 模式卸载时必须提供 --yes。")
        conflict_policy = (
            "用户修改或未受管理的目录会先移动为同级备份"
            if force
            else "用户修改或未受管理的目录将拒绝卸载"
        )
        click.confirm(
            f"将从 {targets[0].path} 卸载 {skill.name} Skill；"
            f"受管理且未修改的安装将被删除，{conflict_policy}。是否继续？",
            abort=True,
        )
    try:
        results = [uninstall_skill(skill, target, force=force) for target in targets]
    except (OSError, SkillInstallError) as exc:
        raise click.ClickException(str(exc)) from exc
    _output_targets("Skill 卸载结果", results, as_json=as_json)


@skill_group.command("export")
@click.argument("skill_name", default="web-presentation")
@click.option("--output", type=click.Path(path_type=Path), help="输出 ZIP 文件路径。")
@click.option("--force", is_flag=True, help="覆盖已存在的导出文件。")
@click.option("--json", "skill_json", is_flag=True, help="以 JSON 输出导出结果。")
@click.pass_context
def skill_export_cmd(
    ctx: click.Context,
    skill_name: str,
    output: Path | None,
    force: bool,
    skill_json: bool,
) -> None:
    """导出根目录包含 SKILL.md 的通用标准 Skill ZIP。"""

    try:
        result = export_skill(get_bundled_skill(skill_name), output, force=force)
    except (KeyError, OSError, RuntimeError, SkillInstallError) as exc:
        raise click.ClickException(str(exc)) from exc
    if skill_json or ctx.obj.get("as_json"):
        print_json(result)
    else:
        print_success(f"已导出 {skill_name} {result['skill_version']}：{result['path']}")
