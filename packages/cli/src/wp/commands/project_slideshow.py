"""文件功能：校验项目与路由放映参数，并按当前服务端能力限制媒体与时间轴扩展。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import click

from wp.client import ApiClient

SLIDESHOW_CAPABILITY_MISSING = "SLIDESHOW_CAPABILITY_MISSING"
SLIDESHOW_MEDIA_CAPABILITY_MISSING = "SLIDESHOW_MEDIA_CAPABILITY_MISSING"
SLIDESHOW_TIMELINE_CAPABILITY_MISSING = "SLIDESHOW_TIMELINE_CAPABILITY_MISSING"
SLIDESHOW_ADVANCE_MODE_UNKNOWN = "SLIDESHOW_ADVANCE_MODE_UNKNOWN"
SLIDESHOW_ADVANCE_MODES = frozenset({"manual", "timer", "media_end", "timeline_end"})


@dataclass(frozen=True)
class AdvanceRequirements:
    """记录本次写入实际需要的媒体/时间轴能力，避免按模式名称猜测。"""

    needs_media_end: bool = False
    needs_media_timeout: bool = False
    needs_timeline_end: bool = False
    needs_timeline_timeout: bool = False

    def merge(self, other: "AdvanceRequirements") -> "AdvanceRequirements":
        """合并多条路由编辑的能力需求。"""

        return AdvanceRequirements(
            needs_media_end=self.needs_media_end or other.needs_media_end,
            needs_media_timeout=self.needs_media_timeout or other.needs_media_timeout,
            needs_timeline_end=self.needs_timeline_end or other.needs_timeline_end,
            needs_timeline_timeout=self.needs_timeline_timeout or other.needs_timeline_timeout,
        )


EMPTY_ADVANCE_REQUIREMENTS = AdvanceRequirements()


def validate_advance_config(value: Any, label: str) -> AdvanceRequirements:
    """校验 advance 结构，返回需要核对的媒体与时间轴能力。"""

    if value is None:
        return EMPTY_ADVANCE_REQUIREMENTS
    if not isinstance(value, dict):
        raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance 必须是对象或 null。")
    mode = value.get("mode")
    if mode not in SLIDESHOW_ADVANCE_MODES:
        raise click.ClickException(
            f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 使用未知翻页模式 {mode!r}；"
            "可用值：manual、timer、media_end、timeline_end。"
        )
    delay = value.get("delay_ms")
    if not isinstance(delay, int) or isinstance(delay, bool):
        raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance.delay_ms 必须是整数。")
    media_timeout = value.get("media_timeout_ms")
    if media_timeout is not None and (not isinstance(media_timeout, int) or isinstance(media_timeout, bool)):
        raise click.ClickException(
            f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance.media_timeout_ms 必须是整数。"
        )
    timeline_timeout = value.get("timeline_timeout_ms")
    if timeline_timeout is not None and (not isinstance(timeline_timeout, int) or isinstance(timeline_timeout, bool)):
        raise click.ClickException(
            f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 的 advance.timeline_timeout_ms 必须是整数。"
        )
    return AdvanceRequirements(
        needs_media_end=mode == "media_end",
        needs_media_timeout="media_timeout_ms" in value,
        needs_timeline_end=mode == "timeline_end",
        needs_timeline_timeout="timeline_timeout_ms" in value,
    )


def require_slideshow_capability(
    client: ApiClient,
    project_id: int,
    requirements: AdvanceRequirements,
) -> None:
    """按服务端能力拒绝未开放的媒体/时间轴模式或字段，避免旧服务收到未知扩展。"""

    if not any(
        (
            requirements.needs_media_end,
            requirements.needs_media_timeout,
            requirements.needs_timeline_end,
            requirements.needs_timeline_timeout,
        )
    ):
        return
    project = client.get(f"/projects/{project_id}")
    workspace_id = project.get("workspace_id") if isinstance(project, dict) else None
    if not isinstance(workspace_id, int):
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 无法确定项目 {project_id} 的工作空间，"
            "不能核对放映能力。"
        )
    response = client.get(f"/workspaces/{workspace_id}/capabilities")
    slideshow = response.get("slideshow") if isinstance(response, dict) else None
    if not isinstance(slideshow, dict):
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 当前服务端未声明放映能力，"
            "不能写入媒体或时间轴配置；请升级服务端后重试。"
        )
    if requirements.needs_media_end and "media_end" not in (slideshow.get("advance_modes") or []):
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 当前服务端尚未开放 media_end 翻页；"
            "未发送任何写入。"
        )
    if requirements.needs_media_timeout and (slideshow.get("schema_version") or 0) < 2:
        raise click.ClickException(
            f"[{SLIDESHOW_MEDIA_CAPABILITY_MISSING}] 当前服务端放映 Schema 低于 2，"
            "不支持 media_timeout_ms；未发送任何写入。"
        )
    advance_modes = slideshow.get("advance_modes") or []
    if requirements.needs_timeline_end and "timeline_end" not in advance_modes:
        raise click.ClickException(
            f"[{SLIDESHOW_TIMELINE_CAPABILITY_MISSING}] 当前服务端尚未开放 timeline_end 翻页；"
            "未发送任何写入，也不会静默改为 timer。"
        )
    if requirements.needs_timeline_timeout and (slideshow.get("schema_version") or 0) < 3:
        raise click.ClickException(
            f"[{SLIDESHOW_TIMELINE_CAPABILITY_MISSING}] 当前服务端放映 Schema 低于 3，"
            "不支持 timeline_timeout_ms；未发送任何写入。"
        )
