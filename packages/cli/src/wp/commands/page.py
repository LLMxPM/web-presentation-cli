"""文件功能：处理页面管理（列表、详情、源码查看、异步创建与归档）。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.commands.screenshot import screenshot_cmd
from wp.commands.validation_input import build_validation_payload
from wp.config import get_profile, load_config
from wp.formatter import print_code, print_error, print_table
from wp.commands.common import (
    confirm_archive,
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    read_text_file,
    require_array,
    require_ids,
    require_object,
    require_success_job,
    resolve_wait_job,
)
from wp.openapi_help import contract, openapi_command

_PAGE_EDITS_FILE_HELP = (
    "页面编辑操作 JSON 数组；每项的 type 只能是 replace_exact、insert_after 或 rewrite_file。"
    " replace_exact 使用 old_text、new_text；insert_after 使用 anchor_text、new_text；"
    "rewrite_file 使用 content。"
)



@click.group("page")
def page_group() -> None:
    """页面管理与 Mutation 任务。"""


@openapi_command(page_group, "list", contract("GET", "/api/v1/projects/{project_id}/pages"))
@click.option("--project-id", "-p", required=True, type=int, help="项目 ID")
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.pass_context
def list_pages_cmd(ctx: click.Context, project_id: int, page: int, page_size: int) -> None:
    """查询指定项目下的页面列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        res = client.get(
            f"/projects/{project_id}/pages",
            params={"page": page, "page_size": page_size, "status": "active"},
        )
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="page_list")
            return

        items = res.get("items", [])
        rows = [[p["id"], p.get("code", "-"), p.get("title", "-"), f"v{p.get('current_version_no', 1)}", p.get("status", "-")] for p in items]
        print_table(f"项目 (ID: {project_id}) 页面列表", ["ID", "编码", "标题", "版本", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取页面列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(page_group, "get", contract("GET", "/api/v1/pages/{page_id}"))
@click.argument("page_id", type=int)
@click.pass_context
def get_page_cmd(ctx: click.Context, page_id: int) -> None:
    """获取指定页面的元数据详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        page = client.get(f"/pages/{page_id}")
        if ctx.obj.get("as_json"):
            output_result(ctx, page, profile="page_detail")
            return

        rows = [
            ["ID", str(page.get("id"))],
            ["编码", str(page.get("code"))],
            ["标题", str(page.get("title"))],
            ["所属项目 ID", str(page.get("project_id"))],
            ["当前版本", f"v{page.get('current_version_no')}"],
            ["状态", str(page.get("status"))],
            ["创建时间", str(page.get("created_at"))],
        ]
        print_table(f"页面 (ID: {page_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取页面失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(page_group, "source", contract("GET", "/api/v1/pages/{page_id}/source"))
@click.argument("page_id", type=int)
@click.pass_context
def get_page_source_cmd(ctx: click.Context, page_id: int) -> None:
    """查看指定页面的当前 Vue SFC 源码。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        data = client.get(f"/pages/{page_id}/source")
        if ctx.obj.get("as_json"):
            output_result(ctx, data, profile="page_source")
            return

        code = data.get("source_code", "")
        print_code(code, lexer="vue", title=f"页面 ID {page_id} 源码 (v{data.get('version_no')})")
    except ApiClientError as err:
        print_error(f"读取页面源码失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(page_group, "update", contract("PATCH", "/api/v1/pages/{page_id}"))
@click.argument("page_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="页面更新 JSON 请求体")
@idempotency_key_option
@click.pass_context
def update_page_cmd(ctx: click.Context, page_id: int, payload_file: str) -> None:
    """更新页面轻量元数据；源码和结构字段必须走 edit。"""

    try:
        payload = require_object(read_json_file(payload_file, label="页面更新载荷"), label="页面更新载荷")
        output_result(ctx, get_client(ctx).patch(f"/pages/{page_id}", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新页面失败", err)


@openapi_command(
    page_group,
    "create",
    contract("POST", "/api/v1/pages"),
    examples=(
        "wp page create --project-id 7 --name \"核心结论\" --file .tmp/web-presentation/page-new.vue --idempotency-key page-7-core",
    ),
)
@click.option("--project-id", "-p", type=int, help="所属项目 ID")
@click.option("--name", "-n", help="页面标题")
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="Vue 源码文件路径")
@click.option("--description", "-d", help="页面描述")
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), help="完整页面创建 JSON 请求体；提供后忽略其它内容参数")
@click.option("--wait/--no-wait", default=True, help="是否等待后台 Worker 编译与诊断完成 (默认等待)")
@idempotency_key_option
@click.pass_context
def create_page_cmd(
    ctx: click.Context,
    project_id: int,
    name: str,
    file_path: str | None,
    description: str | None,
    payload_file: str | None,
    wait: bool,
) -> None:
    """通过 Mutation Job 创建并校验页面；直接参数模式必须提供项目、标题和完整 SFC 文件。"""

    try:
        if payload_file:
            payload = require_object(read_json_file(payload_file, label="页面创建载荷"), label="页面创建载荷")
        else:
            if project_id is None or not name or not file_path:
                raise click.UsageError("未使用 --payload-file 时必须提供 --project-id、--name 和 --file。")
            payload = {
                "project_id": project_id,
                "name": name,
                "source_code": read_text_file(file_path, label="页面源码"),
                "description": description,
            }
        client = get_client(ctx)
        result = resolve_wait_job(client, client.create_page(payload), wait=wait, timeout=120.0)
        if wait:
            require_success_job(result, ctx=ctx)
        output_result(ctx, result)
    except ApiClientError as err:
        handle_api_error("提交页面任务失败", err)


@openapi_command(
    page_group,
    "archive",
    contract("POST", "/api/v1/pages/{page_id}/archive", "提供 PAGE_ID 时"),
    contract("POST", "/api/v1/pages/batch-archive", "提供 --ids-file 时"),
)
@click.argument("page_id", type=int, required=False)
@click.option("--ids-file", type=click.Path(exists=True, dir_okay=False), help="批量归档 ID JSON 数组")
@click.option("--yes", "-y", is_flag=True, help="仅在用户已明确授权归档时跳过交互确认")
@idempotency_key_option
@click.pass_context
def archive_page_cmd(ctx: click.Context, page_id: int | None, ids_file: str | None, yes: bool) -> None:
    """归档单个页面或 JSON 数组指定的一批页面；两种目标输入只能选一种。"""

    try:
        client = get_client(ctx)
        if ids_file:
            ids = require_ids(read_json_file(ids_file, label="归档 ID"))
            confirm_archive(ids, yes=yes, label="页面")
            output_result(ctx, client.post("/pages/batch-archive", json_data={"ids": ids}), profile="archive")
            return
        if page_id is None:
            raise click.UsageError("必须提供 page_id 或 --ids-file。")
        confirm_archive([page_id], yes=yes, label="页面")
        output_result(ctx, client.post(f"/pages/{page_id}/archive"))
    except ApiClientError as err:
        handle_api_error("归档页面失败", err)


@openapi_command(page_group, "copy", contract("POST", "/api/v1/pages/{page_id}/copy"))
@click.argument("page_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="页面复制 JSON 请求体")
@idempotency_key_option
@click.pass_context
def copy_page_cmd(ctx: click.Context, page_id: int, payload_file: str) -> None:
    """复制页面到目标项目。"""

    try:
        payload = require_object(read_json_file(payload_file, label="页面复制载荷"), label="页面复制载荷")
        output_result(ctx, get_client(ctx).copy_page(page_id, payload))
    except ApiClientError as err:
        handle_api_error("复制页面失败", err)


@openapi_command(
    page_group,
    "edit",
    contract("POST", "/api/v1/pages/{page_id}/edits"),
    examples=(
        "wp page edit 21 --base-version-no 3 --edits-file .tmp/web-presentation/edits-21.json --idempotency-key page-21-v3",
    ),
)
@click.argument("page_id", type=int)
@click.option("--edits-file", type=click.Path(exists=True, dir_okay=False), required=True, help=_PAGE_EDITS_FILE_HELP)
@click.option("--base-version-no", type=int, required=True, help="page get/source 返回的最新 current_version_no")
@click.option("--wait/--no-wait", default=True, help="等待任务终态；--no-wait 只返回入队结果")
@click.option("--timeout", type=float, default=120.0, show_default=True, help="等待任务终态的最长秒数")
@idempotency_key_option
@click.pass_context
def edit_page_cmd(ctx: click.Context, page_id: int, edits_file: str, base_version_no: int, wait: bool, timeout: float) -> None:
    """提交页面结构化编辑任务。"""

    try:
        edits = require_array(read_json_file(edits_file, label="页面编辑操作"), label="页面编辑操作")
        payload = {"page_id": page_id, "base_version_no": base_version_no, "edits": edits}
        client = get_client(ctx)
        job = client.edit_page(page_id, payload)
        result = resolve_wait_job(client, job, wait=wait, timeout=timeout)
        if wait:
            require_success_job(result, ctx=ctx)
        output_result(ctx, result)
    except ApiClientError as err:
        handle_api_error("提交页面编辑失败", err)


@page_group.group("version")
def page_version_group() -> None:
    """页面历史版本。"""


@openapi_command(page_version_group, "list", contract("GET", "/api/v1/pages/{page_id}/versions"))
@click.argument("page_id", type=int)
@click.pass_context
def list_page_versions_cmd(ctx: click.Context, page_id: int) -> None:
    """列出页面版本。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/pages/{page_id}/versions"))
    except ApiClientError as err:
        handle_api_error("获取页面版本失败", err)


@openapi_command(page_version_group, "get", contract("GET", "/api/v1/pages/{page_id}/versions/{version_no}"))
@click.argument("page_id", type=int)
@click.argument("version_no", type=int)
@click.pass_context
def get_page_version_cmd(ctx: click.Context, page_id: int, version_no: int) -> None:
    """获取页面指定版本。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/pages/{page_id}/versions/{version_no}"))
    except ApiClientError as err:
        handle_api_error("获取页面版本内容失败", err)


@openapi_command(page_group, "dependencies", contract("GET", "/api/v1/pages/{page_id}/dependencies"))
@click.argument("page_id", type=int)
@click.pass_context
def page_dependencies_cmd(ctx: click.Context, page_id: int) -> None:
    """获取页面当前版本依赖。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/pages/{page_id}/dependencies"))
    except ApiClientError as err:
        handle_api_error("获取页面依赖失败", err)


@openapi_command(
    page_group,
    "validate",
    contract("POST", "/api/v1/validate/entity"),
    examples=(
        "wp --json page validate 21 --mode content --source-file .tmp/web-presentation/page-21.vue --detail",
    ),
)
@click.argument("page_id", type=int)
@click.option(
    "--mode",
    type=click.Choice(["current", "content", "edits"]),
    default=None,
    help="校验模式；省略时按 --source-file 推断 content、按 --edits-file 推断 edits，否则使用 current。",
)
@click.option("--source-file", type=click.Path(exists=True, dir_okay=False), help="content 模式使用的完整候选源码文件")
@click.option("--edits-file", type=click.Path(exists=True, dir_okay=False), help=_PAGE_EDITS_FILE_HELP)
@click.option("--detail", is_flag=True, help="返回更详细的校验诊断")
@click.pass_context
def validate_page_cmd(ctx: click.Context, page_id: int, mode: str | None, source_file: str | None, edits_file: str | None, detail: bool) -> None:
    """校验页面当前或候选源码。"""

    payload = build_validation_payload(
        "page", page_id, mode=mode, source_file=source_file, edits_file=edits_file, detail=detail,
    )
    try:
        output_result(ctx, get_client(ctx).validate_entity(payload), profile="validation", detail=detail)
    except ApiClientError as err:
        handle_api_error("页面校验失败", err)


page_group.add_command(screenshot_cmd)
