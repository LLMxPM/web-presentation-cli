"""文件功能：CLI 总入口，注册全局选项与全部资源子命令。"""

from __future__ import annotations

import click

from wp import __version__
from wp.commands.asset import asset_group
from wp.commands.auth import login_cmd, logout_cmd, whoami_cmd
from wp.commands.component import component_group
from wp.commands.catalog import runtime_kit_group
from wp.commands.font import font_group
from wp.commands.doctor import doctor_cmd
from wp.commands.job import job_group
from wp.commands.page import page_group
from wp.commands.profile import profile_group
from wp.commands.preview import preview_group
from wp.commands.project import project_group
from wp.commands.skill import skill_group
from wp.commands.style import style_group
from wp.commands.theme import theme_group
from wp.commands.workspace import workspace_group
from wp.commands.system import standards_group, system_group


@click.group()
@click.version_option(version=__version__, prog_name="wp")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="让支持表格视图的命令输出 JSON；复杂响应默认也输出 JSON。",
)
@click.option(
    "--raw",
    is_flag=True,
    help="输出 Backend 原始 JSON；与 --json 互斥，并自动启用 JSON 输出。",
)
@click.option("--profile", help="指定使用的 Profile 名称 (默认 default)")
@click.option("--workspace", "-w", "workspace_id", type=int, help="覆盖当前操作的目标工作空间 ID")
@click.pass_context
def main(
    ctx: click.Context,
    as_json: bool,
    raw: bool,
    profile: str | None,
    workspace_id: int | None,
) -> None:
    """Web Presentation 官方命令行工具 (wp) - 面向 AI 演示文稿创作平台。"""

    if as_json and raw:
        raise click.UsageError("--json 与 --raw 不能同时使用。")
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json or raw
    ctx.obj["raw"] = raw
    ctx.obj["profile"] = profile
    ctx.obj["workspace_id"] = workspace_id


# 注册认证与系统命令
main.add_command(login_cmd)
main.add_command(logout_cmd)
main.add_command(whoami_cmd)
main.add_command(doctor_cmd)
main.add_command(profile_group)
main.add_command(skill_group)
main.add_command(system_group)
main.add_command(standards_group)
main.add_command(runtime_kit_group)
main.add_command(font_group)


# 注册各实体资源命令组
main.add_command(workspace_group)
main.add_command(project_group)
main.add_command(page_group)
main.add_command(preview_group)
main.add_command(component_group)
main.add_command(asset_group)
main.add_command(theme_group)
main.add_command(style_group)
main.add_command(job_group)


if __name__ == "__main__":
    main()
