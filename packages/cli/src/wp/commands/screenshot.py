"""文件功能：保存独立静态截图，区分最新内容、历史内容与可恢复的异步截图任务状态。"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import uuid
import click
from wp.client import ApiClient, ApiClientError
from wp.commands.common import idempotency_key_option
from wp.openapi_help import OpenApiHelpCommand, contract
from wp.commands.static_screenshot_job import capture_static_job
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table

@click.command("screenshot", cls=OpenApiHelpCommand)
@click.argument("page_id", type=int)
@click.option("--output", "-o", help="截图保存路径")
@click.option("--screenshot-id", help="历史内容 SHA-256，只下载，不刷新")
@click.option("--job", "use_job", is_flag=True, help="提交独立静态截图任务，不采样动画")
@click.option("--job-id", type=click.IntRange(min=1), help="继续查询已提交的截图任务")
@click.option("--target-version", type=click.IntRange(min=1), help="静态任务的显式页面版本，冲突拒绝")
@click.option("--no-wait", is_flag=True, help="返回任务当前状态，不等待 PNG")
@click.option("--timeout", type=click.FloatRange(min=0), default=120.0, show_default=True, help="等待任务的秒数；超时返回 pending 与 job_id")
@idempotency_key_option
@click.pass_context
def screenshot_cmd(ctx: click.Context, page_id: int, output: str | None, screenshot_id: str | None,
                   use_job: bool, job_id: int | None, target_version: int | None, no_wait: bool, timeout: float) -> None:
    """获取最新静态截图；--job/--no-wait 可提交任务，--job-id 用于恢复查询。"""
    if screenshot_id and (use_job or job_id is not None or target_version is not None or no_wait):
        raise click.UsageError("--screenshot-id 不能与任务选项同时使用。")
    if job_id is not None and target_version is not None:
        raise click.UsageError("--job-id 查询既有任务，不能重设 --target-version。")
    profile = get_profile(load_config(), ctx.obj.get("profile"))
    client = ApiClient(profile, workspace_id=ctx.obj.get("workspace_id"), idempotency_key=ctx.obj.get("idempotency_key"))
    try:
        if screenshot_id:
            _download_screenshot_content(ctx, client, page_id, screenshot_id.strip(), output)
        elif use_job or job_id is not None or target_version is not None or no_wait:
            result, content = capture_static_job(client, page_id=page_id, job_id=job_id, target_version=target_version, timeout=timeout, no_wait=no_wait)
            if content is not None:
                destination = Path(output) if output else Path(f"page-{page_id}-v{result['version_no']}.png")
                if destination.is_dir(): destination /= f"page-{page_id}-v{result['version_no']}.png"
                _write_bytes_atomic(destination, content)
                result.update(saved_file=str(destination.resolve()), size_bytes=len(content))
            _print_capture_result(ctx, result)
            if result["status"] == "failed": raise SystemExit(1)
        else:
            _download_latest_screenshot(ctx, client, page_id, output)
    except ApiClientError as error:
        status = "unavailable" if error.code == "STATIC_PRESENTATION_UNAVAILABLE" else "failed"
        _print_capture_result(ctx, {"page_id": page_id, "status": status, "code": error.code or "PAGE_SCREENSHOT_FAILED", "message": error.message})
        if status == "failed": raise SystemExit(1)
    except OSError as error:
        print_error(f"保存截图失败：{error}", code="SCREENSHOT_FILE_WRITE_FAILED")
        raise SystemExit(1) from error


def _print_capture_result(ctx: click.Context, result: dict) -> None:
    """所有非 PNG 状态保持结构化，不把 unavailable/skipped/pending 当成截图成功。"""
    if ctx.obj.get("as_json"):
        print_json(result)
    else:
        print_table("静态截图结果", ["字段", "值"], [[str(key), str(value)] for key, value in result.items()])


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
        "status": "ready",
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
        "status": "ready",
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


screenshot_cmd.openapi_contracts = (
    contract("GET", "/api/v1/pages/{page_id}/screenshot"),
    contract("GET", "/api/v1/pages/{page_id}/screenshots/{screenshot_id}/content"),
    contract("POST", "/api/v1/pages/{page_id}/screenshot-jobs"),
    contract("GET", "/api/v1/pages/{page_id}/screenshot-jobs/{job_id}"),
    contract("GET", "/api/v1/pages/{page_id}/screenshot-jobs/{job_id}/content"),
)
