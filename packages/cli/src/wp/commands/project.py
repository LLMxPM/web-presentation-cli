"""文件功能：处理项目管理（列表、详情、创建、更新、归档）。"""

from __future__ import annotations

from typing import Any

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

# 路由编辑允许的设置字段；route 只用于定位，不能改名或移动节点。
ROUTE_EDIT_KEYS = frozenset({"route", "order", "hidden", "group_title", "transition", "advance"})
SLIDESHOW_CAPABILITY_MISSING = "SLIDESHOW_CAPABILITY_MISSING"


def _route_write_page_fields(node: dict[str, Any], *, child: bool) -> dict[str, Any]:
    """把页面节点转换为写入 Schema；保留原始覆盖值，过滤只读派生字段。"""

    fields: dict[str, Any] = {
        "route": node.get("route"),
        "order": node.get("order"),
        "hidden": bool(node.get("hidden", False)),
        "page_id": node.get("page_id"),
        "transition": node.get("transition"),
        "advance": node.get("advance"),
    }
    if not child:
        fields = {"route_type": "page", **fields}
    return fields


def build_route_tree_write_payload(tree: Any) -> dict[str, Any]:
    """把 route-tree 响应转换为整树写入载荷，丢弃 id/生效值等只读字段。"""

    if not isinstance(tree, dict) or not isinstance(tree.get("routes"), list):
        raise click.ClickException("路由树响应缺少 routes 数组，无法安全写回。")
    routes: list[dict[str, Any]] = []
    for node in tree["routes"]:
        if not isinstance(node, dict):
            raise click.ClickException("路由树节点不是 JSON 对象，无法安全写回。")
        route_type = node.get("route_type")
        if route_type == "group":
            children = node.get("children") or []
            if not isinstance(children, list):
                raise click.ClickException("分组节点的 children 必须是数组。")
            if any(not isinstance(child, dict) for child in children):
                raise click.ClickException("分组节点的 children 只能包含 JSON 对象。")
            routes.append({
                "route_type": "group",
                "route": node.get("route"),
                "order": node.get("order"),
                "hidden": bool(node.get("hidden", False)),
                "group_title": node.get("group_title"),
                "children": [_route_write_page_fields(child, child=True) for child in children],
            })
        elif route_type == "page":
            routes.append(_route_write_page_fields(node, child=False))
        else:
            raise click.ClickException(f"未知路由节点类型：{route_type}")
    return {"routes": routes}


def require_slideshow_route_tree(tree: dict[str, Any]) -> None:
    """旧服务缺少放映覆盖/生效字段时明确失败，避免整树写回静默覆盖语义。"""

    if not isinstance(tree, dict) or not isinstance(tree.get("routes"), list):
        raise click.ClickException("路由树响应缺少 routes 数组，无法安全写回。")
    nodes = []
    for node in tree.get("routes") or []:
        if not isinstance(node, dict):
            continue
        if node.get("route_type") == "page":
            nodes.append(node)
        elif node.get("route_type") == "group":
            nodes.extend(child for child in node.get("children") or [] if isinstance(child, dict))
    if not nodes:
        return
    if not all("effective_slideshow" in node and "transition" in node and "advance" in node for node in nodes):
        raise click.ClickException(
            f"[{SLIDESHOW_CAPABILITY_MISSING}] 当前服务端未声明放映配置能力，"
            "无法安全保留路由覆盖；请升级服务端后重试。"
        )


def _normalize_route_selector(value: Any) -> str:
    """把编辑选择器统一为不带首尾斜杠的完整路由路径。"""

    if not isinstance(value, str):
        raise click.ClickException("路由编辑的 route 必须是字符串。")
    normalized = value.strip().strip("/")
    if not normalized:
        raise click.ClickException("路由编辑的 route 不能为空。")
    return normalized


def apply_route_edits(payload: dict[str, Any], edits: list[Any]) -> None:
    """按完整路由路径应用排序、隐藏与覆盖编辑；transition/advance 可显式 null。"""

    index: dict[str, tuple[dict[str, Any], dict[str, Any] | None, bool]] = {}
    for node in payload["routes"]:
        index[_normalize_route_selector(node.get("route"))] = (node, None, node["route_type"] == "group")
        for child in node.get("children") or []:
            index[f"{_normalize_route_selector(node.get('route'))}/{_normalize_route_selector(child.get('route'))}"] = (
                child, node, False,
            )
    seen: set[str] = set()
    for edit in edits:
        if not isinstance(edit, dict):
            raise click.ClickException("每条路由编辑必须是 JSON 对象。")
        unknown = set(edit) - ROUTE_EDIT_KEYS
        if unknown:
            raise click.ClickException(f"路由编辑包含未知字段：{', '.join(sorted(unknown))}。")
        selector = _normalize_route_selector(edit.get("route"))
        if selector in seen:
            raise click.ClickException(f"路由编辑重复选择：{selector}。")
        seen.add(selector)
        target = index.get(selector)
        if target is None:
            raise click.ClickException(f"路由不存在：{selector}。")
        node, parent, is_group = target
        if len(edit) == 1:
            raise click.ClickException(f"路由编辑 {selector} 没有提供任何设置。")
        if "group_title" in edit:
            if not is_group or parent is not None:
                raise click.ClickException(f"只有顶层分组可以设置 group_title：{selector}。")
            node["group_title"] = edit["group_title"]
        if "order" in edit:
            order = edit["order"]
            if isinstance(order, bool) or not isinstance(order, int):
                raise click.ClickException(f"路由 {selector} 的 order 必须是整数。")
            node["order"] = order
        if "hidden" in edit:
            hidden = edit["hidden"]
            if not isinstance(hidden, bool):
                raise click.ClickException(f"路由 {selector} 的 hidden 必须是布尔值。")
            node["hidden"] = hidden
        for key in ("transition", "advance"):
            if key not in edit:
                continue
            if is_group:
                raise click.ClickException(f"分组节点不接受 {key} 覆盖：{selector}。")
            value = edit[key]
            if value is not None and not isinstance(value, dict):
                raise click.ClickException(f"路由 {selector} 的 {key} 必须是对象或 null。")
            node[key] = value


@click.group("project")
def project_group() -> None:
    """项目管理操作。"""


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
        if payload_file:
            payload = require_object(read_json_file(payload_file, label="项目载荷"), label="项目载荷")
        else:
            if not name:
                raise click.UsageError("未使用 --payload-file 时必须提供 --name。")
            payload = {"name": name, "description": description}
        output_result(ctx, get_client(ctx).post("/projects", json_data=payload))
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
        payload = require_object(read_json_file(payload_file, label="项目更新载荷"), label="项目更新载荷")
        output_result(ctx, get_client(ctx).patch(f"/projects/{project_id}", json_data=payload))
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
        payload = require_object(read_json_file(payload_file, label="项目配置载荷"), label="项目配置载荷")
        output_result(ctx, get_client(ctx).put(f"/projects/{project_id}/configuration", json_data=payload))
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
        updated = get_client(ctx).patch(f"/projects/{project_id}", json_data={"slideshow": slideshow})
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
    help="路由编辑 JSON 数组；每项用 route 定位，可设置 order、hidden、group_title、transition、advance",
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
        apply_route_edits(payload, edits)
        output_result(ctx, client.put(f"/projects/{project_id}/route-tree", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新项目路由树失败", err)


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
