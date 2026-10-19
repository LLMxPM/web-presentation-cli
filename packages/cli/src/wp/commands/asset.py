"""文件功能：提供工作空间资源的查询、上传、替换、下载、文本内容、复制、更新与归档命令。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO
import uuid

import click

from wp.client import ApiClientError
from wp.commands.common import (
    confirm_archive,
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    read_text_file,
    require_ids,
    require_object,
)
from wp.formatter import print_error, print_success, print_table
from wp.openapi_help import contract, openapi_command


ASSET_TYPES = ["image", "icon", "font", "video", "audio", "drawio", "mermaid", "chart", "formula", "model3d"]

# 音频由服务端同时校验扩展名与 Content-Type；显式声明避免客户端 MIME 猜测差异。
AUDIO_CONTENT_TYPES_BY_EXTENSION = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


def _file_part(
    path: Path,
    file_obj: BinaryIO,
    *,
    asset_type: str | None = None,
) -> tuple[str, BinaryIO] | tuple[str, BinaryIO, str]:
    """构造 multipart 文件片段；音频按扩展名补齐受支持的 Content-Type。"""

    content_type = AUDIO_CONTENT_TYPES_BY_EXTENSION.get(path.suffix.lower())
    if content_type is None or (asset_type is not None and asset_type != "audio"):
        return path.name, file_obj
    return path.name, file_obj, content_type


def _write_bytes_atomic(save_path: Path, content: bytes) -> None:
    """原子写入下载文件，失败时清理临时文件。"""

    tmp_path = save_path.with_name(f".{save_path.name}.tmp.{uuid.uuid4().hex[:8]}")
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(content)
        os.replace(tmp_path, save_path)
    except OSError:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


@click.group("asset")
def asset_group() -> None:
    """工作空间静态资源管理。"""


@openapi_command(asset_group, "list", contract("GET", "/api/v1/assets"))
@click.option("--page", default=1, type=int, show_default=True, help="结果页码")
@click.option("--page-size", default=50, type=int, show_default=True, help="每页返回数量")
@click.option("--type", "asset_type", type=click.Choice(ASSET_TYPES), help="按资源业务类型筛选")
@click.option("--keyword", help="按资源名称、说明或标签搜索")
@click.pass_context
def list_assets_cmd(ctx: click.Context, page: int, page_size: int, asset_type: str | None, keyword: str | None) -> None:
    """查询工作空间资源。"""

    params = {"page": page, "page_size": page_size, "asset_type": asset_type, "keyword": keyword}
    try:
        result = get_client(ctx).get("/assets", params={key: value for key, value in params.items() if value is not None})
        if ctx.obj.get("as_json"):
            output_result(ctx, result, profile="asset_list")
            return
        rows = [[item.get("id"), item.get("name", "-"), item.get("asset_type", "-"), item.get("status", "-")] for item in result.get("items", [])]
        print_table("资源列表", ["ID", "名称", "类型", "状态"], rows)
    except ApiClientError as err:
        handle_api_error("获取资源列表失败", err)


@openapi_command(asset_group, "get", contract("GET", "/api/v1/assets/{asset_id}"))
@click.argument("asset_id", type=int)
@click.pass_context
def get_asset_cmd(ctx: click.Context, asset_id: int) -> None:
    """获取资源详情。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/assets/{asset_id}"), profile="asset_detail")
    except ApiClientError as err:
        handle_api_error("获取资源详情失败", err)


@openapi_command(
    asset_group,
    "download",
    contract("GET", "/api/v1/assets/{asset_id}/file"),
    examples=(
        "wp asset download 42 --output .tmp/web-presentation/product.glb",
        "wp --json asset download 42 --hash <current_file_hash> --output .tmp/web-presentation/product.glb",
    ),
)
@click.argument("asset_id", type=int)
@click.option("--output", "-o", help="保存路径或已存在的目录；默认使用资源 original_name")
@click.option("--hash", "file_hash", help="指定期望的当前 file_hash；与服务端不一致时拒绝下载")
@click.pass_context
def download_asset_cmd(ctx: click.Context, asset_id: int, output: str | None, file_hash: str | None) -> None:
    """下载资源当前或指定版本的原始二进制文件。"""

    try:
        client = get_client(ctx)
        asset = client.get(f"/assets/{asset_id}")
        if not isinstance(asset, dict):
            raise click.ClickException("资源详情响应格式非法。")
        target_hash = str(file_hash or asset.get("file_hash") or "").strip()
        params = {"download": 1}
        if target_hash:
            params["hash"] = target_hash
        headers, content = client.get_bytes(f"/assets/{asset_id}/file", params=params)
        original_name = Path(str(asset.get("original_name") or asset.get("name") or f"asset-{asset_id}")).name
        save_path = Path(output) if output else Path(original_name)
        if save_path.is_dir():
            save_path = save_path / original_name
        try:
            _write_bytes_atomic(save_path, content)
        except OSError as exc:
            print_error(f"写入资源文件 '{save_path}' 失败: {exc}")
            raise SystemExit(1) from exc
        result_payload = {
            "asset_id": asset_id,
            "name": asset.get("name"),
            "asset_type": asset.get("asset_type"),
            "file_hash": target_hash or headers.get("etag"),
            "saved_file": str(save_path.resolve()),
            "size_bytes": len(content),
        }
        if ctx.obj.get("as_json"):
            output_result(ctx, result_payload)
            return
        print_success(f"已下载资源 (ID: {asset_id}) 至 [bold]{save_path}[/bold]")
        print_table(
            "资源下载信息",
            ["属性", "值"],
            [
                ["资源 ID", str(asset_id)],
                ["资源名称", str(asset.get("name") or "-")],
                ["文件 hash", target_hash or "-"],
                ["文件大小", f"{len(content)} 字节"],
                ["保存路径", str(save_path.resolve())],
            ],
        )
    except ApiClientError as err:
        handle_api_error("下载资源文件失败", err)


@openapi_command(
    asset_group,
    "upload",
    contract("POST", "/api/v1/assets"),
    examples=(
        "wp asset upload .tmp/web-presentation/hero-image.png --type image --name hero-image --idempotency-key asset-hero-image",
        "wp asset upload .tmp/web-presentation/transition-forward.mp3 --type audio --name transition-forward --idempotency-key asset-transition-forward",
    ),
)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--type", "asset_type", type=click.Choice(ASSET_TYPES), required=True, help="上传资源类型；音频使用 audio")
@click.option("--name", help="平台逻辑名；默认使用文件名主干")
@click.option("--description", help="资源内容、来源和使用场景说明")
@click.option("--overwrite", is_flag=True, help="显式覆盖同名文件或逻辑名资源；不校验版本基线，需版本保护请用 asset replace；model3d 不支持")
@idempotency_key_option
@click.pass_context
def upload_asset_cmd(ctx: click.Context, file_path: str, asset_type: str, name: str | None, description: str | None, overwrite: bool) -> None:
    """上传二进制、图片、音频或三维模型资源。"""

    path = Path(file_path)
    if overwrite and asset_type == "model3d":
        raise click.UsageError("model3d 不支持 --overwrite，请使用 wp asset replace 并提供 --expected-file-hash。")
    data = {"asset_type": asset_type, "name": name or path.stem, "description": description}
    if overwrite:
        data["overwrite"] = "true"
    try:
        with path.open("rb") as file_obj:
            result = get_client(ctx).upload(
                "/assets",
                files={"file": _file_part(path, file_obj, asset_type=asset_type)},
                data=data,
            )
        output_result(ctx, result)
    except ApiClientError as err:
        message = "上传资源失败"
        if err.code == "ASSET_NAME_CONFLICT":
            message += "；确认覆盖后可加 --overwrite，按 ID 和版本基线替换请用 wp asset replace"
        handle_api_error(message, err)


@openapi_command(
    asset_group,
    "replace",
    contract("POST", "/api/v1/assets/{asset_id}/replace"),
    examples=(
        "wp asset replace 42 .tmp/web-presentation/product-v2.glb --expected-file-hash <current_file_hash> --idempotency-key asset-product-replace",
    ),
)
@click.argument("asset_id", type=int)
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--expected-file-hash", required=True, help="当前资源 file_hash 版本基线；三维资源替换必填")
@idempotency_key_option
@click.pass_context
def replace_asset_cmd(ctx: click.Context, asset_id: int, file_path: str, expected_file_hash: str) -> None:
    """按资源 ID 替换文件内容，保留 id、name 与 asset_type。"""

    path = Path(file_path)
    try:
        with path.open("rb") as file_obj:
            result = get_client(ctx).upload(
                f"/assets/{asset_id}/replace",
                files={"file": _file_part(path, file_obj)},
                data={"expected_file_hash": expected_file_hash.strip()},
            )
        output_result(ctx, result, profile="asset_detail")
    except ApiClientError as err:
        handle_api_error("替换资源文件失败", err)


@openapi_command(
    asset_group,
    "create",
    contract("POST", "/api/v1/assets/content"),
    examples=(
        "wp asset create --payload-file .tmp/web-presentation/asset.json --content-file .tmp/web-presentation/diagram.mmd --idempotency-key asset-diagram",
    ),
)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="文本资源创建 JSON 请求体")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False), help="覆盖 JSON 中 content 的文本文件")
@idempotency_key_option
@click.pass_context
def create_asset_cmd(ctx: click.Context, payload_file: str, content_file: str | None) -> None:
    """创建文本内容资源。"""

    payload = require_object(read_json_file(payload_file, label="资源创建载荷"), label="资源创建载荷")
    if content_file:
        payload["content"] = read_text_file(content_file, label="资源内容")
    try:
        output_result(ctx, get_client(ctx).post("/assets/content", json_data=payload))
    except ApiClientError as err:
        handle_api_error("创建文本资源失败", err)


@asset_group.group("content")
def asset_content_group() -> None:
    """可编辑文本资源内容。"""


@openapi_command(asset_content_group, "get", contract("GET", "/api/v1/assets/{asset_id}/content"))
@click.argument("asset_id", type=int)
@click.pass_context
def get_asset_content_cmd(ctx: click.Context, asset_id: int) -> None:
    """读取资源文本内容。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/assets/{asset_id}/content"))
    except ApiClientError as err:
        handle_api_error("读取资源内容失败", err)


@openapi_command(asset_content_group, "update", contract("PUT", "/api/v1/assets/{asset_id}/content"))
@click.argument("asset_id", type=int)
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False), required=True, help="要写入的完整 UTF-8 文本内容")
@click.option("--change-note", help="本次完整内容替换的变更说明")
@idempotency_key_option
@click.pass_context
def update_asset_content_cmd(ctx: click.Context, asset_id: int, content_file: str, change_note: str | None) -> None:
    """写入资源文本内容。"""

    try:
        output_result(ctx, get_client(ctx).put(f"/assets/{asset_id}/content", json_data={"content": read_text_file(content_file, label="资源内容"), "change_note": change_note}))
    except ApiClientError as err:
        handle_api_error("更新资源内容失败", err)


@openapi_command(asset_content_group, "preview", contract("POST", "/api/v1/assets/{asset_id}/content/preview"))
@click.argument("asset_id", type=int)
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False), required=True, help="用于生成差异且不会写入的候选 UTF-8 文本")
@click.pass_context
def preview_asset_content_cmd(ctx: click.Context, asset_id: int, content_file: str) -> None:
    """预览资源文本内容差异。"""

    try:
        output_result(ctx, get_client(ctx).post(f"/assets/{asset_id}/content/preview", json_data={"content": read_text_file(content_file, label="资源内容")}, idempotent=False))
    except ApiClientError as err:
        handle_api_error("预览资源内容失败", err)


@asset_group.group("tags")
def asset_tags_group() -> None:
    """资源标签。"""


@openapi_command(asset_tags_group, "list", contract("GET", "/api/v1/assets/tags"))
@click.option("--type", "asset_type", type=click.Choice(ASSET_TYPES), help="只返回指定资源类型使用的标签")
@click.pass_context
def list_asset_tags_cmd(ctx: click.Context, asset_type: str | None) -> None:
    """列出工作空间资源标签。"""

    try:
        params = {"asset_type": asset_type} if asset_type else None
        output_result(ctx, get_client(ctx).get("/assets/tags", params=params))
    except ApiClientError as err:
        handle_api_error("获取资源标签失败", err)


@openapi_command(asset_group, "update", contract("PATCH", "/api/v1/assets/{asset_id}"))
@click.argument("asset_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="资源元数据更新 JSON 请求体")
@idempotency_key_option
@click.pass_context
def update_asset_cmd(ctx: click.Context, asset_id: int, payload_file: str) -> None:
    """更新资源元数据。"""

    try:
        output_result(ctx, get_client(ctx).patch(f"/assets/{asset_id}", json_data=require_object(read_json_file(payload_file, label="资源更新载荷"), label="资源更新载荷")))
    except ApiClientError as err:
        handle_api_error("更新资源失败", err)


@openapi_command(asset_group, "copy", contract("POST", "/api/v1/assets/{asset_id}/copy"))
@click.argument("asset_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="资源副本名称、说明等 JSON 请求体")
@idempotency_key_option
@click.pass_context
def copy_asset_cmd(ctx: click.Context, asset_id: int, payload_file: str) -> None:
    """复制资源。"""

    try:
        output_result(ctx, get_client(ctx).post(f"/assets/{asset_id}/copy", json_data=require_object(read_json_file(payload_file, label="资源复制载荷"), label="资源复制载荷")))
    except ApiClientError as err:
        handle_api_error("复制资源失败", err)


@openapi_command(
    asset_group,
    "archive",
    contract("POST", "/api/v1/assets/{asset_id}/archive", "提供 ASSET_ID 时"),
    contract("POST", "/api/v1/assets/batch-archive", "提供 --ids-file 时"),
)
@click.argument("asset_id", type=int, required=False)
@click.option("--ids-file", type=click.Path(exists=True, dir_okay=False), help="批量归档的正整数 ID JSON 数组")
@click.option("--yes", is_flag=True, help="仅在用户已明确授权归档时跳过交互确认")
@idempotency_key_option
@click.pass_context
def archive_asset_cmd(ctx: click.Context, asset_id: int | None, ids_file: str | None, yes: bool) -> None:
    """归档单个资源或 JSON 数组指定的一批资源；两种目标输入只能选一种。"""

    try:
        client = get_client(ctx)
        if ids_file:
            ids = require_ids(read_json_file(ids_file, label="归档 ID"))
            confirm_archive(ids, yes=yes, label="资源")
            output_result(ctx, client.post("/assets/batch-archive", json_data={"ids": ids}), profile="archive")
            return
        if asset_id is None:
            raise click.UsageError("必须提供 asset_id 或 --ids-file。")
        confirm_archive([asset_id], yes=yes, label="资源")
        output_result(ctx, client.post(f"/assets/{asset_id}/archive"))
    except ApiClientError as err:
        handle_api_error("归档资源失败", err)
