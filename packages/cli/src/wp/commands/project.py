"""文件功能：处理项目管理（列表、详情、创建、更新、归档）。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_success, print_table
from wp.commands.common import (
    confirm_archive,
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    require_array,
    require_ids,
    require_object,
)
from wp.openapi_help import contract, openapi_command
from wp.commands.project_audio import (
    gate_audio_settings_in_payload,
    project_audio_group,
)
from wp.commands.project_build import project_build_group
from wp.commands.project_route_add import add_project_route_cmd

from wp.commands.project_route_tree import (
    apply_route_edits,
    build_route_tree_write_payload,
    require_slideshow_route_tree,
)
from wp.commands.project_slideshow import (
    EMPTY_ADVANCE_REQUIREMENTS,
    SLIDESHOW_CAPABILITY_MISSING,
    require_slideshow_capability,
    validate_advance_config,
)


@click.group("project")
def project_group() -> None:
    """项目管理操作。"""


project_group.add_command(project_audio_group)
project_group.add_command(project_build_group)


@openapi_command(project_group, "list", contract("GET", "/api/v1/projects"))
@click.option("--page", "-p", default=1, type=int, help="页码")
@click.option("--page-size", "-s", default=20, type=int, help="每页数量")
@click.option("--keyword", "-k", help="搜索关键字")
@click.pass_context
def list_projects_cmd(ctx: click.Context, page: int, page_size: int, keyword: str | None) -> None:
    """查询工作空间内的项目列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        params = {"page": page, "page_size": page_size, "status": "active"}
        if keyword:
            params["keyword"] = keyword
        res = client.get("/projects", params=params)
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="project_list")
            return

        items = res.get("items", [])
        rows = [[p["id"], p["name"], p.get("status", "-"), p.get("created_at", "-")[:19]] for p in items]
        print_table(f"项目列表 (共 {res.get('total', len(items))} 项)", ["ID", "项目名称", "状态", "创建时间"], rows)
    except ApiClientError as err:
        print_error(f"获取项目列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(project_group, "get", contract("GET", "/api/v1/projects/{project_id}"))
@click.argument("project_id", type=int)
@click.pass_context
def get_project_cmd(ctx: click.Context, project_id: int) -> None:
    """获取单个项目详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        project = client.get(f"/projects/{project_id}")
        if ctx.obj.get("as_json"):
            output_result(ctx, project, profile="project_detail")
            return

        print_success(f"项目详情: [bold]{project.get('name')}[/bold] (ID: {project_id})")
        rows = [
            ["ID", str(project.get("id"))],
            ["名称", str(project.get("name"))],
            ["描述", str(project.get("description") or "-")],
            ["工作空间 ID", str(project.get("workspace_id"))],
            ["工作空间名称", str(project.get("workspace_name") or "-")],
            ["主题 Key", str(project.get("theme_key") or "-")],
            ["路由页面数", str(project.get("routed_page_count", 0))],
            ["页面总数", str(project.get("total_page_count", 0))],
            ["状态", str(project.get("status"))],
            ["创建时间", str(project.get("created_at"))],
        ]
        print_table("基本属性", ["字段", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取项目详情失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(
    project_group,
    "create",
    contract("POST", "/api/v1/projects"),
    examples=('wp project create --name "季度复盘" --idempotency-key project-quarterly-review',),
)
@click.option("--name", "-n", help="项目名称")
@click.option("--description", "-d", help="项目描述")
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), help="完整项目 JSON 请求体；提供后忽略 --name 和 --description")
@idempotency_key_option
@click.pass_context
def create_project_cmd(ctx: click.Context, name: str | None, description: str | None, payload_file: str | None) -> None:
    """创建新项目；未使用 --payload-file 时必须提供 --name。"""

    try:
        client = get_client(ctx)
        if payload_file:
            payload = require_object(read_json_file(payload_file, label="项目载荷"), label="项目载荷")
            gate_audio_settings_in_payload(client, payload, workspace_id=client.workspace_id)
        else:
            if not name:
                raise click.UsageError("未使用 --payload-file 时必须提供 --name。")
            payload = {"name": name, "description": description}
        output_result(ctx, client.post("/projects", json_data=payload))
    except ApiClientError as err:
        handle_api_error("创建项目失败", err)


@openapi_command(project_group, "update", contract("PATCH", "/api/v1/projects/{project_id}"))
@click.argument("project_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="项目更新 JSON 请求体")
@idempotency_key_option
@click.pass_context
def update_project_cmd(ctx: click.Context, project_id: int, payload_file: str) -> None:
    """更新项目元数据或基础配置。"""

    try:
        client = get_client(ctx)
        payload = require_object(read_json_file(payload_file, label="项目更新载荷"), label="项目更新载荷")
        gate_audio_settings_in_payload(client, payload, project_id=project_id)
        output_result(ctx, client.patch(f"/projects/{project_id}", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新项目失败", err)


@project_group.group("configuration")
def project_configuration_group() -> None:
    """项目结构化展示配置。"""


@openapi_command(project_configuration_group, "get", contract("GET", "/api/v1/projects/{project_id}/configuration"))
@click.argument("project_id", type=int)
@click.pass_context
def get_project_configuration_cmd(ctx: click.Context, project_id: int) -> None:
    """获取项目配置。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/projects/{project_id}/configuration"))
    except ApiClientError as err:
        handle_api_error("获取项目配置失败", err)


@openapi_command(
    project_configuration_group,
    "update",
    contract("PUT", "/api/v1/projects/{project_id}/configuration"),
    examples=(
        "wp project configuration update 7 --payload-file .tmp/web-presentation/project-7-configuration.json --idempotency-key project-7-config",
    ),
)
@click.argument("project_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="项目配置 JSON 请求体")
@idempotency_key_option
@click.pass_context
def update_project_configuration_cmd(ctx: click.Context, project_id: int, payload_file: str) -> None:
    """更新项目展示配置。"""

    try:
        client = get_client(ctx)
        payload = require_object(read_json_file(payload_file, label="项目配置载荷"), label="项目配置载荷")
        gate_audio_settings_in_payload(client, payload, project_id=project_id)
        output_result(ctx, client.put(f"/projects/{project_id}/configuration", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新项目配置失败", err)


@project_group.group("slideshow")
def project_slideshow_group() -> None:
    """项目默认放映配置（动画、翻页、循环与自动开始）。"""


@openapi_command(project_slideshow_group, "get", contract("GET", "/api/v1/projects/{project_id}"))
@click.argument("project_id", type=int)
@click.pass_context
def get_project_slideshow_cmd(ctx: click.Context, project_id: int) -> None:
    """读取项目默认放映配置。"""

    try:
        project = get_client(ctx).get(f"/projects/{project_id}")
        if "slideshow" not in project:
            raise click.ClickException(
                f"[{SLIDESHOW_CAPABILITY_MISSING}] 当前服务端未声明放映配置能力；请升级服务端后重试。"
            )
        output_result(ctx, project.get("slideshow"))
    except ApiClientError as err:
        handle_api_error("获取项目放映配置失败", err)


@openapi_command(
    project_slideshow_group,
    "update",
    contract("PATCH", "/api/v1/projects/{project_id}"),
    examples=(
        "wp project slideshow update 7 --slideshow-file .tmp/web-presentation/slideshow-7.json --idempotency-key project-7-slideshow",
    ),
)
@click.argument("project_id", type=int)
@click.option(
    "--slideshow-file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="完整放映配置 JSON；可直接提供 slideshow 对象或包含 slideshow 字段的对象",
)
@idempotency_key_option
@click.pass_context
def update_project_slideshow_cmd(ctx: click.Context, project_id: int, slideshow_file: str) -> None:
    """替换项目默认放映配置；必须提供完整对象，不存在的字段不会被猜测补全。"""

    try:
        payload = require_object(read_json_file(slideshow_file, label="放映配置"), label="放映配置")
        slideshow = payload.get("slideshow", payload)
        if not isinstance(slideshow, dict):
            raise click.ClickException("放映配置必须是完整 JSON 对象。")
        requirements = validate_advance_config(slideshow.get("advance"), "slideshow")
        client = get_client(ctx)
        require_slideshow_capability(client, project_id, requirements)
        updated = client.patch(f"/projects/{project_id}", json_data={"slideshow": slideshow})
        if "slideshow" not in updated:
            raise click.ClickException(
                f"[{SLIDESHOW_CAPABILITY_MISSING}] 服务端未返回放映配置，可能不支持该能力；请升级服务端后重试。"
            )
        output_result(ctx, updated["slideshow"])
    except ApiClientError as err:
        handle_api_error("更新项目放映配置失败", err)


@project_group.group("route")
def project_route_group() -> None:
    """项目路由树。"""


@openapi_command(project_route_group, "get", contract("GET", "/api/v1/projects/{project_id}/route-tree"))
@click.argument("project_id", type=int)
@click.pass_context
def get_project_route_cmd(ctx: click.Context, project_id: int) -> None:
    """获取项目路由树。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/projects/{project_id}/route-tree"))
    except ApiClientError as err:
        handle_api_error("获取项目路由树失败", err)


@openapi_command(
    project_route_group,
    "replace",
    contract("PUT", "/api/v1/projects/{project_id}/route-tree"),
    examples=(
        "wp project route replace 7 --route-file .tmp/web-presentation/route-tree.json --idempotency-key project-7-route",
    ),
)
@click.argument("project_id", type=int)
@click.option("--route-file", type=click.Path(exists=True, dir_okay=False), required=True, help="完整路由树 JSON 文件")
@idempotency_key_option
@click.pass_context
def replace_project_route_cmd(ctx: click.Context, project_id: int, route_file: str) -> None:
    """整体替换项目路由树。"""

    try:
        payload = require_object(read_json_file(route_file, label="路由树"), label="路由树")
        output_result(ctx, get_client(ctx).put(f"/projects/{project_id}/route-tree", json_data=payload))
    except ApiClientError as err:
        handle_api_error("替换项目路由树失败", err)


@openapi_command(
    project_route_group,
    "update",
    contract("GET", "/api/v1/projects/{project_id}/route-tree"),
    contract("PUT", "/api/v1/projects/{project_id}/route-tree"),
    examples=(
        "wp project route update 7 --edit-file .tmp/web-presentation/route-edits-7.json --idempotency-key project-7-route-edit",
    ),
)
@click.argument("project_id", type=int)
@click.option(
    "--edit-file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="只修改已有节点的 JSON 数组；可设置 order、hidden、group_title、transition、advance；新增页面用 route add，整树编排用 route replace",
)
@idempotency_key_option
@click.pass_context
def update_project_route_cmd(ctx: click.Context, project_id: int, edit_file: str) -> None:
    """读取当前路由树，应用编辑后整树写回；自动保留原始覆盖并过滤只读生效值。"""

    try:
        client = get_client(ctx)
        tree = client.get(f"/projects/{project_id}/route-tree")
        require_slideshow_route_tree(tree)
        payload = build_route_tree_write_payload(tree)
        edits = require_array(read_json_file(edit_file, label="路由编辑"), label="路由编辑")
        requirements = EMPTY_ADVANCE_REQUIREMENTS
        for index, edit in enumerate(edits):
            if not isinstance(edit, dict) or "advance" not in edit:
                continue
            requirements = requirements.merge(validate_advance_config(edit.get("advance"), f"编辑[{index}]"))
        require_slideshow_capability(client, project_id, requirements)
        apply_route_edits(payload, edits)
        output_result(ctx, client.put(f"/projects/{project_id}/route-tree", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新项目路由树失败", err)


project_route_group.add_command(add_project_route_cmd)


@openapi_command(project_group, "apply-style", contract("POST", "/api/v1/projects/{project_id}/apply-style"))
@click.argument("project_id", type=int)
@click.option("--style-id", type=int, required=True, help="要复制为项目独立配置快照的工作空间样式 ID")
@idempotency_key_option
@click.pass_context
def apply_project_style_cmd(ctx: click.Context, project_id: int, style_id: int) -> None:
    """将样式方案应用到项目。"""

    try:
        output_result(ctx, get_client(ctx).post(f"/projects/{project_id}/apply-style", json_data={"style_id": style_id}))
    except ApiClientError as err:
        handle_api_error("应用项目样式失败", err)


@project_group.group("build-assets")
def project_build_assets_group() -> None:
    """项目构建额外资源配置，不启动构建。"""


@openapi_command(project_build_assets_group, "update", contract("PUT", "/api/v1/projects/{project_id}/build-assets"))
@click.argument("project_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="包含完整额外资源名称列表的 JSON 请求体")
@idempotency_key_option
@click.pass_context
def update_project_build_assets_cmd(ctx: click.Context, project_id: int, payload_file: str) -> None:
    """更新项目构建额外资源配置。"""

    try:
        payload = require_object(read_json_file(payload_file, label="构建资源配置"), label="构建资源配置")
        output_result(ctx, get_client(ctx).put(f"/projects/{project_id}/build-assets", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新项目构建资源配置失败", err)


@openapi_command(
    project_group,
    "archive",
    contract("POST", "/api/v1/projects/{project_id}/archive", "提供 PROJECT_ID 时"),
    contract("POST", "/api/v1/projects/batch-archive", "提供 --ids-file 时"),
)
@click.argument("project_id", type=int, required=False)
@click.option("--ids-file", type=click.Path(exists=True, dir_okay=False), help="批量归档 ID JSON 数组")
@click.option("--yes", "-y", is_flag=True, help="仅在用户已明确授权归档时跳过交互确认")
@idempotency_key_option
@click.pass_context
def archive_project_cmd(ctx: click.Context, project_id: int | None, ids_file: str | None, yes: bool) -> None:
    """归档单个项目或 JSON 数组指定的一批项目；两种目标输入只能选一种。"""

    try:
        client = get_client(ctx)
        if ids_file:
            ids = require_ids(read_json_file(ids_file, label="归档 ID"))
            confirm_archive(ids, yes=yes, label="项目")
            output_result(ctx, client.post("/projects/batch-archive", json_data={"ids": ids}), profile="archive")
            return
        if project_id is None:
            raise click.UsageError("必须提供 project_id 或 --ids-file。")
        confirm_archive([project_id], yes=yes, label="项目")
        output_result(ctx, client.post(f"/projects/{project_id}/archive"))
    except ApiClientError as err:
        handle_api_error("归档项目失败", err)
