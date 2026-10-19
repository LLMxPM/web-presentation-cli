"""文件功能：转换路由树写模型并应用已有节点编辑，保留逐页放映覆盖。"""

from __future__ import annotations

from typing import Any

import click

from wp.commands.project_slideshow import SLIDESHOW_CAPABILITY_MISSING

ROUTE_EDIT_KEYS = frozenset({"route", "order", "hidden", "group_title", "transition", "advance"})


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
            raise click.ClickException(
                f"路由编辑包含未知字段：{', '.join(sorted(unknown))}。"
                "route update 只修改已有节点；新增页面请用 wp project route add，整树编排请用 route replace。"
            )
        selector = _normalize_route_selector(edit.get("route"))
        if selector in seen:
            raise click.ClickException(f"路由编辑重复选择：{selector}。")
        seen.add(selector)
        target = index.get(selector)
        if target is None:
            raise click.ClickException(f"路由不存在：{selector}。新增页面请用 wp project route add，整树编排请用 route replace。")
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
