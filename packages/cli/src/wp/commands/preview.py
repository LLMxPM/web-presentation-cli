"""文件功能：提供统一的项目与单页面预览地址获取命令。"""

from __future__ import annotations

import click

from wp.client import ApiClientError
from wp.commands.common import get_client, handle_api_error, output_result
from wp.openapi_help import contract, openapi_command

_REQUIRED_PREVIEW_FIELDS = (
    "preview_url",
    "artifact_id",
    "preview_kind",
    "entry_descriptor",
    "viewport_width",
    "viewport_height",
)


@click.group("preview")
def preview_group() -> None:
    """获取项目或页面的短期预览地址。"""


@openapi_command(
    preview_group,
    "get",
    contract("POST", "/api/v1/projects/{project_id}/preview-artifact", "使用 --project-id 时"),
    contract("POST", "/api/v1/pages/{page_id}/preview-artifact", "使用 --page-id 时"),
    contract(
        "POST",
        "/api/v1/pages/{page_id}/versions/{version_no}/preview-artifact",
        "使用 --page-id 与 --version 时",
    ),
    examples=(
        "wp preview get --project-id 7",
        "wp preview get --project-id 7 --route overview",
        "MSYS_NO_PATHCONV=1 wp preview get --project-id 7 --route /overview",
        "wp preview get --page-id 21",
        "wp preview get --page-id 21 --version 5",
    ),
)
@click.option("--project-id", type=int, help="创建整项目预览的项目 ID")
@click.option("--page-id", type=click.IntRange(min=1), help="创建单页面预览的页面 ID")
@click.option(
    "--version",
    "version_no",
    type=click.IntRange(min=1),
    help="页面历史版本号；只能与 --page-id 搭配，预览目标版本的源码与备注",
)
@click.option(
    "--route",
    help="项目预览的入口路由，例如 overview（不带前导斜杠）；Git Bash 需要保留前导斜杠时使用 MSYS_NO_PATHCONV=1",
)
@click.pass_context
def get_preview_cmd(
    ctx: click.Context,
    project_id: int | None,
    page_id: int | None,
    version_no: int | None,
    route: str | None,
) -> None:
    """获取项目、单页面或页面历史版本的预览地址；项目与页面目标只能选择一种。"""

    if (project_id is None) == (page_id is None):
        raise click.UsageError("必须且只能提供 --project-id 或 --page-id。")
    if page_id is not None and route is not None:
        raise click.UsageError("--route 只适用于项目预览，请改用 --project-id。")
    if version_no is not None and page_id is None:
        raise click.UsageError("--version 只适用于页面历史版本预览，必须同时提供 --page-id。")

    target_type = "project" if project_id is not None else "page"
    target_id = project_id if project_id is not None else page_id
    try:
        client = get_client(ctx)
        if version_no is not None:
            result = client.create_page_version_preview_artifact(page_id, version_no)
        else:
            result = client.create_preview_artifact(
                target_type=target_type,
                target_id=target_id,
                route=route,
            )
        if not isinstance(result, dict) or any(
            field not in result or result[field] in (None, "") for field in _REQUIRED_PREVIEW_FIELDS
        ):
            missing = [field for field in _REQUIRED_PREVIEW_FIELDS if not isinstance(result, dict) or result.get(field) in (None, "")]
            raise click.ClickException(f"预览响应缺少必要字段: {', '.join(missing)}")
        if version_no is not None and not ctx.obj.get("raw"):
            # 目标身份字段只补充进 --json 稳定投影；--raw 必须保持 Backend 原始响应。
            result = {**result, "page_id": page_id, "version_no": version_no}
        output_result(ctx, result, profile="preview")
    except ApiClientError as err:
        handle_api_error("获取预览地址失败", err)
