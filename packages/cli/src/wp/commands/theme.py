"""文件功能：处理主题管理（列表、详情、创建、复制、归档）。"""

from __future__ import annotations

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_table
from wp.commands.common import (
    confirm_archive,
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    require_ids,
    require_object,
)
from wp.openapi_help import contract, openapi_command


@click.group("theme")
def theme_group() -> None:
    """工作空间主题管理。"""


@openapi_command(theme_group, "list", contract("GET", "/api/v1/themes"))
@click.option("--page", default=1, type=int, help="页码")
@click.option("--page-size", default=50, type=int, help="每页数量")
@click.pass_context
def list_themes_cmd(ctx: click.Context, page: int, page_size: int) -> None:
    """查询工作空间的主题列表。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        res = client.get("/themes", params={"page": page, "page_size": page_size})
        if ctx.obj.get("as_json"):
            output_result(ctx, res, profile="theme")
            return

        items = res.get("items", [])
        rows = [[t["id"], t.get("key", "-"), t.get("name", "-"), t.get("status", "-")] for t in items]
        print_table("主题列表", ["ID", "Key", "名称", "状态"], rows)
    except ApiClientError as err:
        print_error(f"获取主题列表失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(theme_group, "get", contract("GET", "/api/v1/themes/{theme_id}"))
@click.argument("theme_id", type=int)
@click.pass_context
def get_theme_cmd(ctx: click.Context, theme_id: int) -> None:
    """获取单个主题详情。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        theme = client.get(f"/themes/{theme_id}")
        if ctx.obj.get("as_json"):
            output_result(ctx, theme, profile="theme")
            return

        def _format_asset(asset: object, asset_id: object) -> str:
            if isinstance(asset, dict) and asset.get("name"):
                return f"{asset.get('name')} (ID: {asset.get('id')})"
            if asset_id is not None:
                return f"ID: {asset_id}"
            return "-"

        def _format_font(family: object, label: object) -> str:
            if isinstance(family, dict) and family.get("name"):
                return f"族: {family.get('name')} (ID: {family.get('id')})"
            if label is not None:
                return f"预设: {label}"
            return "-"

        rows = [
            ["ID", str(theme.get("id"))],
            ["Key", str(theme.get("key"))],
            ["名称", str(theme.get("name"))],
            ["描述", str(theme.get("description") or "-")],
            ["品牌 Logo", _format_asset(theme.get("logo_asset"), theme.get("logo_asset_id"))],
            ["反色 Logo", _format_asset(theme.get("invert_logo_asset"), theme.get("invert_logo_asset_id"))],
            ["项目图标", _format_asset(theme.get("project_icon_asset"), theme.get("project_icon_asset_id"))],
            ["标题字体", _format_font(theme.get("heading_font_family"), theme.get("heading_font_label"))],
            ["正文字体", _format_font(theme.get("body_font_family"), theme.get("body_font_label"))],
            ["代码字体", _format_font(theme.get("code_font_family"), theme.get("code_font_label"))],
        ]
        print_table(f"主题 (ID: {theme_id}) 详情", ["属性", "值"], rows)
    except ApiClientError as err:
        print_error(f"获取主题失败: {err.message}", code=err.code)
        raise SystemExit(1)


@openapi_command(
    theme_group,
    "create",
    contract("POST", "/api/v1/themes"),
    examples=(
        'wp theme create --key light-corporate --name "企业浅色" --idempotency-key theme-light-corporate',
        'wp theme create --payload-file theme-brand.json --idempotency-key theme-brand-1',
    ),
)
@click.option("--key", "-k", help="主题唯一标识 (例如 light-corporate)")
@click.option("--name", "-n", help="主题名称")
@click.option("--description", "-d", help="主题描述")
@click.option(
    "--payload-file",
    type=click.Path(exists=True, dir_okay=False),
    help="完整主题 JSON 请求体（支持配置 logo_asset_id、invert_logo_asset_id、project_icon_asset_id、heading_font_family_id、body_font_preset 等设计字段）；提供后忽略命令行 key/name/description",
)
@idempotency_key_option
@click.pass_context
def create_theme_cmd(ctx: click.Context, key: str | None, name: str | None, description: str | None, payload_file: str | None) -> None:
    """创建新主题；直接参数模式必须提供不可变 key 和名称。"""

    try:
        if payload_file:
            payload = require_object(read_json_file(payload_file, label="主题创建载荷"), label="主题创建载荷")
        else:
            if not key or not name:
                raise click.UsageError("未使用 --payload-file 时必须提供 --key 和 --name。")
            payload = {"key": key, "name": name, "description": description}
        output_result(ctx, get_client(ctx).post("/themes", json_data=payload), profile="theme")
    except ApiClientError as err:
        handle_api_error("创建主题失败", err)


@openapi_command(
    theme_group,
    "update",
    contract("PATCH", "/api/v1/themes/{theme_id}"),
    examples=(
        'wp theme update 1 --payload-file update-palette.json --idempotency-key upd-theme-1',
        'wp theme update 1 --payload-file clear-logo-switch-font.json --idempotency-key upd-theme-2',
    ),
)
@click.argument("theme_id", type=int)
@click.option(
    "--payload-file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="主题更新 JSON 请求体（支持更新名称、说明、色板，清空图片传 null，切换字体族传 family_id 或预设传 preset；禁止修改 key）",
)
@idempotency_key_option
@click.pass_context
def update_theme_cmd(ctx: click.Context, theme_id: int, payload_file: str) -> None:
    """更新主题设计配置（支持图片槽位清空/替换与三槽字体切换；禁止修改 key）。"""

    try:
        output_result(
            ctx,
            get_client(ctx).patch(
                f"/themes/{theme_id}",
                json_data=require_object(read_json_file(payload_file, label="主题更新载荷"), label="主题更新载荷"),
            ),
            profile="theme",
        )
    except ApiClientError as err:
        handle_api_error("更新主题失败", err)


@openapi_command(theme_group, "copy", contract("POST", "/api/v1/themes/{theme_id}/copy"))
@click.argument("theme_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="新主题 key、名称和说明 JSON 请求体")
@idempotency_key_option
@click.pass_context
def copy_theme_cmd(ctx: click.Context, theme_id: int, payload_file: str) -> None:
    """复制主题。"""

    try:
        output_result(ctx, get_client(ctx).post(f"/themes/{theme_id}/copy", json_data=require_object(read_json_file(payload_file, label="主题复制载荷"), label="主题复制载荷")))
    except ApiClientError as err:
        handle_api_error("复制主题失败", err)


@openapi_command(
    theme_group,
    "archive",
    contract("POST", "/api/v1/themes/{theme_id}/archive", "提供 THEME_ID 时"),
    contract("POST", "/api/v1/themes/batch-archive", "提供 --ids-file 时"),
)
@click.argument("theme_id", type=int, required=False)
@click.option("--ids-file", type=click.Path(exists=True, dir_okay=False), help="批量归档的正整数 ID JSON 数组")
@click.option("--yes", "-y", is_flag=True, help="仅在用户已明确授权归档时跳过交互确认")
@idempotency_key_option
@click.pass_context
def archive_theme_cmd(ctx: click.Context, theme_id: int | None, ids_file: str | None, yes: bool) -> None:
    """归档单个主题或 JSON 数组指定的一批主题；两种目标输入只能选一种。"""

    try:
        client = get_client(ctx)
        if ids_file:
            ids = require_ids(read_json_file(ids_file, label="归档 ID"))
            confirm_archive(ids, yes=yes, label="主题")
            output_result(ctx, client.post("/themes/batch-archive", json_data={"ids": ids}), profile="archive")
            return
        if theme_id is None:
            raise click.UsageError("必须提供 theme_id 或 --ids-file。")
        confirm_archive([theme_id], yes=yes, label="主题")
        output_result(ctx, client.post(f"/themes/{theme_id}/archive"))
    except ApiClientError as err:
        handle_api_error("归档主题失败", err)
