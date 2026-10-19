"""文件功能：提供页面最新截图与按内容 ID 下载历史截图的保存命令。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import uuid

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table


def _write_bytes_atomic(save_path: Path, content: bytes) -> None:
    """原子写入截图，失败时清理临时文件。"""

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


def _content_identity(headers: object, content: bytes) -> str:
    """优先返回服务端 ETag，缺失时退回本地 SHA-256，并明确这是内容身份。"""

    etag = ""
    if hasattr(headers, "get"):
        etag = str(headers.get("etag") or "").strip().strip('"')
    return etag or hashlib.sha256(content).hexdigest()


@click.command("screenshot")
@click.argument("page_id", type=int)
@click.option("--output", "-o", help="截图输出保存路径")
@click.option(
    "--screenshot-id",
    help="按内容 ID（页面范围内的 SHA-256）下载历史截图；只下载，不刷新页面截图",
)
@click.pass_context
def screenshot_cmd(
    ctx: click.Context,
    page_id: int,
    output: str | None,
    screenshot_id: str | None,
) -> None:
    """获取指定页面的最新截图；提供 --screenshot-id 时只下载该内容，不刷新最新截图。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"))

    try:
        if screenshot_id:
            _download_screenshot_content(ctx, client, page_id, screenshot_id.strip(), output)
            return
        _download_latest_screenshot(ctx, client, page_id, output)
    except ApiClientError as err:
        action = "下载截图内容" if screenshot_id else "获取最新截图"
        print_error(f"{action}失败: {err.message}", code=err.code)
        raise SystemExit(1)


def _download_screenshot_content(
    ctx: click.Context,
    client: ApiClient,
    page_id: int,
    screenshot_id: str,
    output: str | None,
) -> None:
    """按内容 ID 下载截图；不存在时保留 404，不回退最新截图。"""

    headers, img_bytes = client.get_page_screenshot_content(page_id=page_id, screenshot_id=screenshot_id)
    save_path = Path(output) if output else Path(f"page-{page_id}-{screenshot_id[:12]}.png")
    if save_path.is_dir():
        save_path = save_path / f"page-{page_id}-{screenshot_id[:12]}.png"
    try:
        _write_bytes_atomic(save_path, img_bytes)
    except OSError as exc:
        print_error(f"写入截图文件 '{save_path}' 失败: {exc}")
        raise SystemExit(1) from exc

    content_hash = _content_identity(headers, img_bytes)
    payload = {
        "page_id": page_id,
        "screenshot_id": screenshot_id,
        "content_hash": content_hash,
        "saved_file": str(save_path.resolve()),
        "size_bytes": len(img_bytes),
        # 历史内容接口不提供页面版本；明确未知，不用当前版本猜测。
        "version_no": None,
    }
    if ctx.obj.get("as_json"):
        print_json(payload)
        return
    print_success(f"已下载页面 (ID: {page_id}) 截图 [bold]{screenshot_id}[/bold] 至 [bold]{save_path}[/bold]")
    print_table(
        "截图内容信息",
        ["属性", "值"],
        [
            ["页面 ID", str(page_id)],
            ["截图内容 ID", screenshot_id],
            ["内容 hash", content_hash or "-"],
            ["页面版本", "未知（历史内容接口不返回版本）"],
            ["文件大小", f"{len(img_bytes)} 字节"],
            ["保存路径", str(save_path.resolve())],
        ],
    )


def _download_latest_screenshot(
    ctx: click.Context,
    client: ApiClient,
    page_id: int,
    output: str | None,
) -> None:
    """刷新并保存最新截图，保留原有 page:read + preview:run 流程。"""

    page_meta, img_bytes = client.get_latest_page_screenshot(page_id=page_id)
    version_no = page_meta.get("version_no") or 1
    save_path = Path(output) if output else Path(f"page-{page_id}-v{version_no}.png")
    if save_path.is_dir():
        save_path = save_path / f"page-{page_id}-v{version_no}.png"
    try:
        _write_bytes_atomic(save_path, img_bytes)
    except OSError as exc:
        print_error(f"写入截图文件 '{save_path}' 失败: {exc}")
        raise SystemExit(1) from exc

    result_payload = {
        "page_id": page_id,
        "version_no": version_no,
        "saved_file": str(save_path.resolve()),
        "size_bytes": len(img_bytes),
    }
    if ctx.obj.get("as_json"):
        print_json(result_payload)
        return
    print_success(f"成功获取页面 (ID: {page_id}) 最新截图并保存至 [bold]{save_path}[/bold]")
    rows = [
        ["页面 ID", str(page_id)],
        ["页面版本", f"v{version_no}"],
        ["文件大小", f"{len(img_bytes)} 字节"],
        ["保存路径", str(save_path.resolve())],
    ]
    print_table("最新页面截图信息", ["属性", "值"], rows)
