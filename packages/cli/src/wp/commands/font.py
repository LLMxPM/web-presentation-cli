"""文件功能：提供工作空间注册字体管理命令（列表、详情、注册、更新与内嵌字体族子命令）。"""

from __future__ import annotations

import click

from wp.client import ApiClientError
from wp.commands.common import (
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    require_object,
)
from wp.commands.font_family import family_group
from wp.formatter import print_table
from wp.openapi_help import contract, openapi_command


@click.group("font")
def font_group() -> None:
    """工作空间注册字体管理。"""


@openapi_command(font_group, "list", contract("GET", "/api/v1/fonts"))
@click.option("--page", default=1, type=int, show_default=True, help="结果页码")
@click.option("--page-size", default=50, type=int, show_default=True, help="每页返回数量")
@click.option("--keyword", help="按字体名称或逻辑名搜索")
@click.pass_context
def font_list_cmd(ctx: click.Context, page: int, page_size: int, keyword: str | None) -> None:
    """查询工作空间注册字体列表。"""

    params: dict[str, int | str] = {"page": page, "page_size": page_size}
    if keyword:
        params["keyword"] = keyword
    try:
        res = get_client(ctx).list_fonts(params=params)
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="font_face")
            return

        items = res.get("items", []) if isinstance(res, dict) else []
        rows = [
            [
                item.get("id"),
                item.get("family_name", "-"),
                item.get("asset_id", "-"),
                item.get("font_format", "-"),
                item.get("font_weight", "-"),
                item.get("font_style", "-"),
                item.get("font_display", "-"),
                item.get("status", "-"),
            ]
            for item in items
        ]
        print_table("字体 Face 列表", ["ID", "族名", "资源ID", "格式", "字重", "样式", "显示", "状态"], rows)
    except ApiClientError as err:
        handle_api_error("获取字体列表失败", err)


@openapi_command(font_group, "get", contract("GET", "/api/v1/fonts/{font_id}"))
@click.argument("font_id", type=int)
@click.pass_context
def font_get_cmd(ctx: click.Context, font_id: int) -> None:
    """查询单个注册字体详情。"""

    try:
        res = get_client(ctx).get_font(font_id)
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="font_face")
            return

        rows = [
            ["ID", str(res.get("id"))],
            ["所属族名", str(res.get("family_name") or "-")],
            ["字体族 ID", str(res.get("family_id") or "-")],
            ["资产 ID", str(res.get("asset_id") or "-")],
            ["资产名称", str(res.get("asset_name") or "-")],
            ["格式", str(res.get("font_format") or "-")],
            ["字重", str(res.get("font_weight") or "-")],
            ["样式", str(res.get("font_style") or "-")],
            ["显示策略", str(res.get("font_display") or "-")],
            ["状态", str(res.get("status") or "-")],
            ["创建时间", str(res.get("created_at") or "-")],
            ["更新时间", str(res.get("updated_at") or "-")],
        ]
        print_table(f"字体 (ID: {font_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        handle_api_error("获取字体详情失败", err)


@openapi_command(
    font_group,
    "register",
    contract("POST", "/api/v1/fonts"),
    examples=('wp font register --payload-file font-register.json --idempotency-key reg-font-1',),
)
@click.option(
    "--payload-file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="字体注册 JSON 请求体（必须包含 asset_id、family_name，可选 font_format/font_weight/font_style/font_display）",
)
@idempotency_key_option
@click.pass_context
def font_register_cmd(ctx: click.Context, payload_file: str) -> None:
    """注册已有字体资源为字体项。"""

    try:
        payload = require_object(read_json_file(payload_file, label="字体注册载荷"), label="字体注册载荷")
        output_result(ctx, get_client(ctx).register_font(payload), profile="font_face")
    except ApiClientError as err:
        handle_api_error("注册字体失败", err)


@openapi_command(
    font_group,
    "update",
    contract("PATCH", "/api/v1/fonts/{font_id}"),
    examples=('wp font update 1 --payload-file font-update.json --idempotency-key upd-font-1',),
)
@click.argument("font_id", type=int)
@click.option(
    "--payload-file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="字体更新 JSON 请求体（可修改 family_name 或字重/样式等配置）",
)
@idempotency_key_option
@click.pass_context
def font_update_cmd(ctx: click.Context, font_id: int, payload_file: str) -> None:
    """更新注册字体配置或所属族。"""

    try:
        payload = require_object(read_json_file(payload_file, label="字体更新载荷"), label="字体更新载荷")
        output_result(ctx, get_client(ctx).update_font(font_id, payload), profile="font_face")
    except ApiClientError as err:
        handle_api_error("更新字体失败", err)


# 挂载字体族命令组
font_group.add_command(family_group, "family")
