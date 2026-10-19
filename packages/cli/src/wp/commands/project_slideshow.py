"""文件功能：校验项目与路由放映参数，并按当前服务端能力限制媒体扩展。"""

from __future__ import annotations

from typing import Any

import click

from wp.client import ApiClient

SLIDESHOW_CAPABILITY_MISSING = "SLIDESHOW_CAPABILITY_MISSING"
SLIDESHOW_MEDIA_CAPABILITY_MISSING = "SLIDESHOW_MEDIA_CAPABILITY_MISSING"
SLIDESHOW_ADVANCE_MODE_UNKNOWN = "SLIDESHOW_ADVANCE_MODE_UNKNOWN"
SLIDESHOW_ADVANCE_MODES = frozenset({"manual", "timer", "media_end"})


def validate_advance_config(value: Any, label: str) -> tuple[bool, bool]:
    """校验 advance 结构，返回是否需要 media_end 与媒体时限能力。"""

    if value is None:
        return False, False
    if not isinstance(value, dict):
        raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance 必须是对象或 null。")
    mode = value.get("mode")
    if mode not in SLIDESHOW_ADVANCE_MODES:
        raise click.ClickException(
            f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 使用未知翻页模式 {mode!r}；"
            "可用值：manual、timer、media_end。"
        )
    delay = value.get("delay_ms")
    if not isinstance(delay, int) or isinstance(delay, bool):
        raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance.delay_ms 必须是整数。")
    timeout = value.get("media_timeout_ms")
    if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool)):
        raise click.ClickException(
            f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance.media_timeout_ms 必须是整数。"
        )
    return mode == "media_end", "media_timeout_ms" in value


def require_slideshow_media_capability(
    client: ApiClient,
    project_id: int,
    *,
    needs_media_end: bool,
    needs_media_timeout: bool,
) -> None:
    """按服务端能力拒绝未开放的媒体模式或字段，避免旧服务收到未知扩展。"""

    if not needs_media_end and not needs_media_timeout:
        return
    project = client.get(f"/projects/{project_id}")
    workspace_id = project.get("workspace_id") if isinstance(project, dict) else None
    if not isinstance(workspace_id, int):
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 无法确定项目 {project_id} 的工作空间，"
            "不能核对媒体放映能力。"
        )
    response = client.get(f"/workspaces/{workspace_id}/capabilities")
    slideshow = response.get("slideshow") if isinstance(response, dict) else None
    if not isinstance(slideshow, dict):
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 当前服务端未声明放映能力，"
            "不能写入媒体模式或媒体时限；请升级服务端后重试。"
        )
    if needs_media_end and "media_end" not in (slideshow.get("advance_modes") or []):
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 当前服务端尚未开放 media_end 翻页；"
            "未发送任何写入。"
        )
    if needs_media_timeout and (slideshow.get("schema_version") or 0) < 2:
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 当前服务端放映 Schema 低于 2，"
            "不支持 media_timeout_ms；未发送任何写入。"
        )
