"""文件功能：通过读取并保留当前路由树，给项目追加顶层页面或分组子页面。"""

from __future__ import annotations

import re

import click

from wp.client import ApiClientError
from wp.commands.common import get_client, handle_api_error, idempotency_key_option, output_result
from wp.commands.project_route_tree import build_route_tree_write_payload, require_slideshow_route_tree
from wp.openapi_help import OpenApiHelpCommand, contract


def route_segment(_ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    """校验新增节点和父分组只能使用单段相对路径，避免意外嵌套或路径转换。"""

    if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise click.BadParameter("必须是单段相对路径，例如 overview 或 chapter-1，不能包含斜杠。", param=param)
    return value


@click.command("add", cls=OpenApiHelpCommand)
@click.argument("project_id", type=int)
@click.option("--page-id", required=True, type=click.IntRange(min=1), help="当前项目中的真实页面 ID")
@click.option("--route", required=True, callback=route_segment, help="新页面的单段相对路由，如 overview")
@click.option("--parent", callback=route_segment, help="已有顶层分组的 route；省略时追加为顶层页面")
@click.option("--order", type=int, help="同级排序值；省略时使用当前同级最大值加 1")
@click.option("--hidden", is_flag=True, help="隐藏新增页面的导航入口")
@idempotency_key_option
@click.pass_context
def add_project_route_cmd(
    ctx: click.Context, project_id: int, page_id: int, route: str,
    parent: str | None, order: int | None, hidden: bool,
) -> None:
    """挂载一个已有页面，保留其它节点及放映覆盖；不要并发修改同一项目路由。"""

    try:
        client = get_client(ctx)
        tree = client.get(f"/projects/{project_id}/route-tree")
        require_slideshow_route_tree(tree)
        payload = build_route_tree_write_payload(tree)
        siblings = payload["routes"]
        if parent is not None:
            group = next((node for node in siblings if node["route"] == parent), None)
            if group is None or group["route_type"] != "group":
                raise click.ClickException(f"父分组不存在或不是分组：{parent}。新建分组请使用 route replace。")
            siblings = group["children"]
        existing = next((node for node in siblings if node["route"] == route), None)
        if existing is not None:
            if (existing.get("page_id") == page_id and existing["hidden"] == hidden
                    and (order is None or existing["order"] == order)):
                output_result(ctx, tree)
                return
            raise click.ClickException(f"同级路由已存在：{route}。修改已有节点请使用 route update。")
        node = {
            "route": route, "page_id": page_id, "hidden": hidden,
            "order": order if order is not None else max((item["order"] for item in siblings), default=-1) + 1,
        }
        if parent is None:
            node["route_type"] = "page"
        siblings.append(node)
        output_result(ctx, client.put(f"/projects/{project_id}/route-tree", json_data=payload))
    except ApiClientError as err:
        handle_api_error("新增项目路由失败", err)


add_project_route_cmd.openapi_contracts = (
    contract("GET", "/api/v1/projects/{project_id}/route-tree"),
    contract("PUT", "/api/v1/projects/{project_id}/route-tree"),
)
add_project_route_cmd.help_examples = (
    "wp project route add 7 --page-id 42 --route overview --idempotency-key project-7-route-overview",
    "wp project route add 7 --page-id 43 --route details --parent chapter-1 --idempotency-key project-7-route-details",
)
