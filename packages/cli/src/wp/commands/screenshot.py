"""文件功能：提供页面最新截图、历史内容与临时时间点截图的保存命令。"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
import uuid

import click

from wp.client import ApiClient, ApiClientError
from wp.commands.common import idempotency_key_option
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json, print_success, print_table

MOTION_TERMINAL_FAILURES = frozenset({"failed", "skipped", "cancelled"})
MOTION_POLL_INTERVAL_SECONDS = 0.5


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
@click.option("--motion-timeline-id", help="临时时间点截图：页面时间轴 ID；与 --motion-label 或 --motion-at-ms 一起使用")
@click.option("--motion-label", help="临时时间点截图：时间轴标签")
@click.option("--motion-at-ms", type=int, help="临时时间点截图：绝对毫秒位置")
@click.option("--motion-offset-ms", type=int, default=None, help="临时时间点截图：相对标签的毫秒偏移")
@click.option(
    "--motion-visual-mode",
    type=click.Choice(["full", "reduced"]),
    default=None,
    help="临时时间点截图：视觉模式，默认 full",
)
@click.option("--target-version", type=int, default=None, help="临时时间点截图：显式页面版本，冲突时拒绝")
@click.option("--timeout", type=float, default=120.0, show_default=True, help="临时截图任务等待秒数")
@idempotency_key_option
@click.pass_context
def screenshot_cmd(
    ctx: click.Context,
    page_id: int,
    output: str | None,
    screenshot_id: str | None,
    motion_timeline_id: str | None,
    motion_label: str | None,
    motion_at_ms: int | None,
    motion_offset_ms: int | None,
    motion_visual_mode: str | None,
    target_version: int | None,
    timeout: float,
) -> None:
    """获取指定页面的最新截图；提供 --screenshot-id 时只下载该内容，不刷新最新截图。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    client = ApiClient(
        profile,
        workspace_id=ctx.obj.get("workspace_id"),
        idempotency_key=ctx.obj.get("idempotency_key"),
    )
    motion_requested = any(
        value is not None
        for value in (
            motion_timeline_id,
            motion_label,
            motion_at_ms,
            motion_offset_ms,
            motion_visual_mode,
            target_version,
        )
    )

    try:
        if screenshot_id:
            _download_screenshot_content(ctx, client, page_id, screenshot_id.strip(), output)
            return
        if motion_requested:
            _download_motion_screenshot(
                ctx,
                client,
                page_id=page_id,
                timeline_id=motion_timeline_id,
                label=motion_label,
                at_ms=motion_at_ms,
                offset_ms=motion_offset_ms,
                visual_mode=motion_visual_mode,
                target_version=target_version,
                timeout=timeout,
                output=output,
            )
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


def _require_motion_capability(client: ApiClient, page_id: int) -> int:
    """读取页面与工作空间能力；时间轴临时截图未开放时不发送任何写入。"""

    page = client.get(f"/pages/{page_id}")
    workspace_id = page.get("workspace_id") if isinstance(page, dict) else None
    if not isinstance(workspace_id, int):
        raise click.ClickException(
            "[TIMELINE_CAPTURE_CAPABILITY_MISSING] 无法确定页面所属工作空间，不能核对时间轴截图能力。"
        )
    capabilities = client.get(f"/workspaces/{workspace_id}/capabilities")
    timeline = capabilities.get("timeline") if isinstance(capabilities, dict) else None
    if (
        not isinstance(timeline, dict)
        or timeline.get("enabled") is not True
        or timeline.get("capture_snapshot") is not True
    ):
        raise click.ClickException(
            "[TIMELINE_CAPTURE_CAPABILITY_MISSING] 当前服务端尚未开放 timeline.capture_snapshot；"
            "未发送任何截图任务。请升级服务端或继续使用默认最新截图。"
        )
    return workspace_id


def _build_motion_snapshot(
    *,
    timeline_id: str | None,
    label: str | None,
    at_ms: int | None,
    offset_ms: int | None,
    visual_mode: str | None,
) -> dict[str, object]:
    """收敛 CLI 选项为协议选择器，拒绝静默丢字段或同时提交两种时间位置。"""

    if not timeline_id or not timeline_id.strip():
        raise click.BadParameter("提供临时时间点截图时必须提供 --motion-timeline-id。")
    if (label is None) == (at_ms is None):
        raise click.BadParameter("--motion-label 与 --motion-at-ms 必须且只能提供一个。")
    if offset_ms is not None and label is None:
        raise click.BadParameter("--motion-offset-ms 只能与 --motion-label 一起使用。")
    if at_ms is not None and at_ms < 0:
        raise click.BadParameter("--motion-at-ms 不能为负数。")
    selector: dict[str, object] = {"timeline_id": timeline_id.strip(), "visual_mode": visual_mode or "full"}
    if label is not None:
        selector["at_label"] = label.strip()
    if at_ms is not None:
        selector["at_ms"] = at_ms
    if offset_ms is not None:
        selector["offset_ms"] = offset_ms
    return selector


def _download_motion_screenshot(
    ctx: click.Context,
    client: ApiClient,
    *,
    page_id: int,
    timeline_id: str | None,
    label: str | None,
    at_ms: int | None,
    offset_ms: int | None,
    visual_mode: str | None,
    target_version: int | None,
    timeout: float,
    output: str | None,
) -> None:
    """提交临时截图任务并等待终态，再读取任务内容；能力关闭时不发送写入。"""

    selector = _build_motion_snapshot(
        timeline_id=timeline_id,
        label=label,
        at_ms=at_ms,
        offset_ms=offset_ms,
        visual_mode=visual_mode,
    )
    _require_motion_capability(client, page_id)
    payload: dict[str, object] = {"motion_snapshot": selector}
    if target_version is not None:
        payload["target_page_version_no"] = target_version
    job = client.post(f"/pages/{page_id}/screenshot-jobs", json_data=payload)
    if not isinstance(job, dict):
        raise click.ClickException("[PAGE_SCREENSHOT_JOB_INVALID] 服务端未返回截图任务对象。")
    job_id = job.get("job_id")
    if not isinstance(job_id, int):
        raise click.ClickException("[PAGE_SCREENSHOT_JOB_INVALID] 服务端未返回合法 job_id。")

    terminal = _wait_motion_job(client, page_id=page_id, job_id=job_id, timeout=timeout)
    result = terminal.get("result") if isinstance(terminal, dict) else None
    if not isinstance(result, dict):
        raise click.ClickException("[PAGE_SCREENSHOT_JOB_INVALID] 截图任务成功但缺少结果摘要。")
    screenshot_id = str(result.get("screenshot_id") or "")
    if not screenshot_id:
        raise click.ClickException("[PAGE_SCREENSHOT_JOB_INVALID] 截图任务成功但缺少内容身份。")

    headers, img_bytes = client.get_bytes(f"/pages/{page_id}/screenshot-jobs/{job_id}/content")
    content_type = str(headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if "image/png" not in content_type:
        raise click.ClickException(f"[INVALID_CONTENT_TYPE] 服务端响应 Content-Type 异常 ('{content_type}')，预期为 image/png")
    save_path = Path(output) if output else Path(f"page-{page_id}-motion-{screenshot_id[:12]}.png")
    if save_path.is_dir():
        save_path = save_path / f"page-{page_id}-motion-{screenshot_id[:12]}.png"
    try:
        _write_bytes_atomic(save_path, img_bytes)
    except OSError as exc:
        print_error(f"写入截图文件 '{save_path}' 失败: {exc}")
        raise SystemExit(1) from exc

    response = {
        "page_id": page_id,
        "job_id": job_id,
        "screenshot_id": screenshot_id,
        "version_no": result.get("version_no"),
        "applied_motion": result.get("applied_motion"),
        "saved_file": str(save_path.resolve()),
        "size_bytes": len(img_bytes),
    }
    if ctx.obj.get("as_json"):
        print_json(response)
        return
    print_success(f"已生成页面 (ID: {page_id}) 临时间点截图并保存至 [bold]{save_path}[/bold]")
    rows = [
        ["页面 ID", str(page_id)],
        ["任务 ID", str(job_id)],
        ["截图内容 ID", screenshot_id],
        ["页面版本", f"v{result.get('version_no')}" if result.get("version_no") else "-"],
        ["时间轴", str(selector.get("timeline_id"))],
        ["时间位置", _format_motion_position(selector)],
        ["文件大小", f"{len(img_bytes)} 字节"],
        ["保存路径", str(save_path.resolve())],
    ]
    print_table("临时页面截图信息", ["属性", "值"], rows)


def _format_motion_position(selector: dict[str, object]) -> str:
    """把选择器格式化为可读时间位置，保留 offset 语义。"""

    if "at_ms" in selector:
        return f"{selector['at_ms']}ms"
    label = str(selector.get("at_label") or "")
    offset = selector.get("offset_ms")
    return f"{label} + {offset}ms" if offset is not None else label


def _wait_motion_job(
    client: ApiClient,
    *,
    page_id: int,
    job_id: int,
    timeout: float,
) -> dict[str, object]:
    """轮询截图任务终态；失败与超时保留服务端错误码，不回退默认截图。"""

    deadline = time.monotonic() + max(0.1, timeout)
    while True:
        job = client.get(f"/pages/{page_id}/screenshot-jobs/{job_id}")
        if not isinstance(job, dict):
            raise click.ClickException("[PAGE_SCREENSHOT_JOB_INVALID] 服务端未返回截图任务对象。")
        status = str(job.get("status") or "")
        if status == "succeeded":
            return job
        if status in MOTION_TERMINAL_FAILURES:
            error = job.get("error") if isinstance(job.get("error"), dict) else {}
            print_error(
                f"临时间点截图任务失败: {error.get('message') or status}",
                code=error.get("code") or "PAGE_SCREENSHOT_JOB_FAILED",
            )
            raise SystemExit(1)
        if time.monotonic() >= deadline:
            raise click.ClickException(
                f"[PAGE_SCREENSHOT_JOB_TIMEOUT] 截图任务 {job_id} 在 {timeout:g} 秒内未完成；"
                "任务仍可能继续运行，可稍后重试读取。"
            )
        time.sleep(MOTION_POLL_INTERVAL_SECONDS)
