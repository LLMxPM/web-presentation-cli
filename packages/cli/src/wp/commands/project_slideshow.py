"""文件功能：严格校验 schema 4 的 Scene 放映参数，并拒绝把新配置写入未声明该版本的服务。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import click
from wp.client import ApiClient

SLIDESHOW_CAPABILITY_MISSING = "SLIDESHOW_CAPABILITY_MISSING"
SLIDESHOW_ADVANCE_MODE_UNKNOWN = "SLIDESHOW_ADVANCE_MODE_UNKNOWN"
SLIDESHOW_ADVANCE_MODES = frozenset({"manual", "timer", "scene_end"})

@dataclass(frozen=True)
class AdvanceRequirements:
    """只记录是否写入新 advance；空覆盖恢复继承，不需要额外能力判断。"""
    schema4: bool = False
    def merge(self, other: "AdvanceRequirements") -> "AdvanceRequirements":
        """合并整批编辑，写入前一次核对服务版本。"""
        return AdvanceRequirements(self.schema4 or other.schema4)

EMPTY_ADVANCE_REQUIREMENTS = AdvanceRequirements()

def validate_advance_config(value: Any, label: str) -> AdvanceRequirements:
    """只接受三种模式及严格整数，旧模式/字段明确报错，不降级为定时推进。"""
    if value is None:
        return EMPTY_ADVANCE_REQUIREMENTS
    if not isinstance(value, dict) or set(value) - {"mode", "delay_ms", "completion_delay_ms"}:
        raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label}.advance 必须是 schema 4 对象，旧模式与超时字段已删除。")
    if value.get("mode") not in SLIDESHOW_ADVANCE_MODES:
        raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label} 只支持 manual/timer/scene_end。")
    for key, minimum, default in (("delay_ms", 1000, None), ("completion_delay_ms", 0, 300)):
        number = value.get(key, default)
        if isinstance(number, bool) or not isinstance(number, int) or not minimum <= number <= 3600000:
            raise click.ClickException(f"[{SLIDESHOW_ADVANCE_MODE_UNKNOWN}] {label}.advance.{key} 必须是 {minimum}–3600000 的整数。")
    return AdvanceRequirements(True)

def require_slideshow_capability(client: ApiClient, project_id: int, requirements: AdvanceRequirements) -> None:
    """只有服务明确声明 schema 4 和三种模式时才提交新 advance，缺失时写入前失败。"""
    if not requirements.schema4:
        return
    project = client.get(f"/projects/{project_id}")
    workspace_id = project.get("workspace_id") if isinstance(project, dict) else None
    if isinstance(workspace_id, bool) or not isinstance(workspace_id, int):
        raise click.ClickException(f"[{SLIDESHOW_CAPABILITY_MISSING}] 无法确定项目工作空间，未发送写入。")
    response = client.get(f"/workspaces/{workspace_id}/capabilities")
    capability = response.get("slideshow") if isinstance(response, dict) else None
    if not isinstance(capability, dict) or capability.get("schema_version") != 4 or not SLIDESHOW_ADVANCE_MODES.issubset(set(capability.get("advance_modes") or [])):
        raise click.ClickException(f"[{SLIDESHOW_CAPABILITY_MISSING}] 服务端必须声明放映 schema 4 与 manual/timer/scene_end；未发送写入，不静默降级。")


def validate_slideshow_config(value: Any) -> AdvanceRequirements:
    """完整对象只允许当前三组字段，不能把旧自动开始或半对象交给写入。"""
    if not isinstance(value, dict) or set(value) != {"transition", "advance", "loop"} or not isinstance(value.get("loop"), bool) or value.get("advance") is None:
        raise click.ClickException("[SLIDESHOW_CONFIG_INVALID] 必须提供 transition/advance/loop 完整对象，旧自动开始字段已删除。")
    transition = value.get("transition")
    if not isinstance(transition, dict) or set(transition) != {"effect", "duration_ms"}:
        raise click.ClickException("[SLIDESHOW_CONFIG_INVALID] transition 必须包含 effect/duration_ms。")
    effect, duration = transition["effect"], transition["duration_ms"]
    if isinstance(duration, bool) or not isinstance(duration, int) or not (effect == "none" and duration == 0 or effect in {"fade", "push"} and 100 <= duration <= 2000):
        raise click.ClickException("[SLIDESHOW_CONFIG_INVALID] 非法翻页过渡。")
    return validate_advance_config(value["advance"], "slideshow")
