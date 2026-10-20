"""文件功能：提供工作空间字体族管理命令（列表、详情与重命名）。"""

from __future__ import annotations

import click

from wp.client import ApiClientError
from wp.commands.common import (
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
)
from wp.formatter import print_table
from wp.openapi_help import contract, openapi_command


@click.group("family")
def family_group() -> None:
    """工作空间字体族管理。"""


@openapi_command(family_group, "list", contract("GET", "/api/v1/font-families"))
@click.option("--page", default=1, type=int, show_default=True, help="结果页码")
@click.option("--page-size", default=50, type=int, show_default=True, help="每页返回数量")
@click.option("--keyword", help="按字体族名称搜索")
@click.pass_context
def family_list_cmd(ctx: click.Context, page: int, page_size: int, keyword: str | None) -> None:
    """查询工作空间字体族列表。"""

    params: dict[str, int | str] = {"page": page, "page_size": page_size}
    if keyword:
        params["keyword"] = keyword
    try:
        res = get_client(ctx).list_font_families(params=params)
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="font_family")
            return

        items = res.get("items", []) if isinstance(res, dict) else []
        rows = [
            [
                item.get("id"),
                item.get("name", "-"),
                len(item.get("faces", [])),
                item.get("created_at", "-"),
            ]
            for item in items
        ]
        print_table("字体族列表", ["ID", "族名", "包含 Face 数", "创建时间"], rows)
    except ApiClientError as err:
        handle_api_error("获取字体族列表失败", err)


@openapi_command(family_group, "get", contract("GET", "/api/v1/font-families/{family_id}"))
@click.argument("family_id", type=int)
@click.pass_context
def family_get_cmd(ctx: click.Context, family_id: int) -> None:
    """查询单个字体族详情及关联 Face 列表。"""

    try:
        res = get_client(ctx).get_font_family(family_id)
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="font_family")
            return

        rows = [
            ["ID", str(res.get("id"))],
            ["族名", str(res.get("name") or "-")],
            ["包含 Face 数", str(len(res.get("faces", [])))],
            ["创建时间", str(res.get("created_at") or "-")],
            ["更新时间", str(res.get("updated_at") or "-")],
        ]
        print_table(f"字体族 (ID: {family_id}) 详情", ["属性", "值"], rows)

        faces = res.get("faces", [])
        if faces:
            face_rows = [
                [
                    fc.get("id"),
                    fc.get("asset_id", "-"),
                    fc.get("asset_name", "-"),
                    fc.get("font_format", "-"),
                    fc.get("font_weight", "-"),
                    fc.get("font_style", "-"),
                    fc.get("font_display", "-"),
                    fc.get("status", "-"),
                ]
                for fc in faces
            ]
            print_table(
                f"族 '{res.get('name')}' 关联 Face 列表",
                ["Face ID", "资源ID", "资源名称", "格式", "字重", "样式", "显示", "状态"],
                face_rows,
            )
    except ApiClientError as err:
        handle_api_error("获取字体族详情失败", err)


@openapi_command(
    family_group,
    "rename",
    contract("PATCH", "/api/v1/font-families/{family_id}"),
    examples=('wp font family rename 1 --name "新族名" --idempotency-key ren-fam-1',),
)
@click.argument("family_id", type=int)
@click.option("--name", "-n", required=True, help="新的字体族名称")
@idempotency_key_option
@click.pass_context
def family_rename_cmd(ctx: click.Context, family_id: int, name: str) -> None:
    """重命名字体族。"""

    try:
        output_result(
            ctx,
            get_client(ctx).rename_font_family(family_id, name),
            profile="font_family",
        )
    except ApiClientError as err:
        handle_api_error("重命名字体族失败", err)
