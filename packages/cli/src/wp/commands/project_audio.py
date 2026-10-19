"""文件功能：项目音频音量与 cue 绑定命令，包含能力门禁、严格写模型和原子清空。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import click

from wp.client import ApiClient, ApiClientError
from wp.commands.common import (
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    require_object,
)
from wp.formatter import print_success, print_table
from wp.openapi_help import contract, openapi_command

AUDIO_VOLUME_FIELDS = (
    "master_volume_percent",
    "narration_volume_percent",
    "effects_volume_percent",
)
AUDIO_SETTINGS_FIELDS = frozenset((*AUDIO_VOLUME_FIELDS, "cue_bindings"))
CUE_BINDING_WRITE_FIELDS = frozenset({"key", "asset_id", "gain_percent"})
AUDIO_CAPABILITY_MISSING = "AUDIO_CAPABILITY_MISSING"
AUDIO_CUES_NOT_OPEN = "AUDIO_CUES_NOT_OPEN"


def _validate_percent(value: Any, label: str) -> int:
    """校验 0–100 的严格整数百分比。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise click.ClickException(f"{label} 必须是 0 到 100 的整数。")
    if value < 0 or value > 100:
        raise click.ClickException(f"{label} 必须在 0 到 100 之间。")
    return value


def normalize_audio_settings_payload(value: Any, *, label: str = "音频设置") -> dict[str, Any]:
    """把文件载荷收敛为服务端写模型，拒绝只读字段、未知字段、null 与缺失音量。"""

    settings = require_object(value, label=label)
    unknown = set(settings) - AUDIO_SETTINGS_FIELDS
    if unknown:
        raise click.ClickException(
            f"{label}包含未知字段：{', '.join(sorted(unknown))}；"
            "读取响应中的 asset_name、asset_type、asset_status 等只读字段不能写回。"
        )
    missing = [field for field in AUDIO_VOLUME_FIELDS if field not in settings]
    if missing:
        raise click.ClickException(f"{label}缺少音量字段：{', '.join(missing)}。")
    normalized: dict[str, Any] = {
        field: _validate_percent(settings[field], field) for field in AUDIO_VOLUME_FIELDS
    }
    raw_bindings = settings.get("cue_bindings")
    if not isinstance(raw_bindings, list):
        raise click.ClickException(f"{label}.cue_bindings 必须是数组；清空请显式提交 []。")
    bindings: list[dict[str, Any]] = []
    for index, item in enumerate(raw_bindings):
        if not isinstance(item, Mapping):
            raise click.ClickException(f"{label}.cue_bindings[{index}] 必须是 JSON 对象。")
        unknown_binding = set(item) - CUE_BINDING_WRITE_FIELDS
        if unknown_binding:
            raise click.ClickException(
                f"{label}.cue_bindings[{index}] 包含只读字段或未知字段："
                f"{', '.join(sorted(unknown_binding))}；写入只接受 key、asset_id 与 gain_percent。"
            )
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise click.ClickException(f"{label}.cue_bindings[{index}].key 必须是非空字符串。")
        asset_id = item.get("asset_id")
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 1:
            raise click.ClickException(f"{label}.cue_bindings[{index}].asset_id 必须是正整数。")
        binding: dict[str, Any] = {"key": key, "asset_id": asset_id}
        if "gain_percent" in item:
            binding["gain_percent"] = _validate_percent(
                item["gain_percent"], f"{label}.cue_bindings[{index}].gain_percent"
            )
        bindings.append(binding)
    normalized["cue_bindings"] = bindings
    return normalized


def has_cue_bindings(settings: Mapping[str, Any]) -> bool:
    """判断写入载荷是否包含至少一个 cue 绑定。"""

    bindings = settings.get("cue_bindings")
    return isinstance(bindings, list) and bool(bindings)


def load_audio_capability(client: ApiClient, workspace_id: int) -> dict[str, Any]:
    """读取工作空间音频能力；字段缺失或 Schema 未知时显式失败，不推测支持。"""

    response = client.get(f"/workspaces/{workspace_id}/capabilities")
    slideshow = response.get("slideshow") if isinstance(response, dict) else None
    audio = slideshow.get("audio") if isinstance(slideshow, dict) else None
    if (
        not isinstance(audio, dict)
        or not isinstance(audio.get("audio_cues"), bool)
        or audio.get("schema_version") != 1
    ):
        raise click.ClickException(
            f"[{AUDIO_CAPABILITY_MISSING}] 当前服务端未声明可识别的音频能力，"
            "不能确认 audio_cues 是否开放；请升级服务端后重试。"
        )
    return audio


def _resolve_workspace_id(
    client: ApiClient,
    *,
    project_id: int | None,
    workspace_id: int | None = None,
) -> int:
    """定位项目所属工作空间；无法确定时拒绝能力判断。"""

    if workspace_id is not None:
        return workspace_id
    if project_id is not None:
        project = client.get(f"/projects/{project_id}")
        project_workspace_id = project.get("workspace_id") if isinstance(project, dict) else None
        if isinstance(project_workspace_id, int):
            return project_workspace_id
    if isinstance(client.workspace_id, int):
        return client.workspace_id
    raise click.ClickException(
        f"[{AUDIO_CAPABILITY_MISSING}] 无法确定目标工作空间，不能核对 audio_cues 能力。"
    )


def ensure_audio_cues_write_allowed(
    client: ApiClient,
    audio_settings: Mapping[str, Any],
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
) -> None:
    """含非空 cue 绑定的写入必须先确认 audio_cues 已开放；空绑定不受限制。"""

    if not has_cue_bindings(audio_settings):
        return
    resolved_workspace_id = _resolve_workspace_id(
        client,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    capability = load_audio_capability(client, resolved_workspace_id)
    if capability["audio_cues"] is not True:
        raise click.ClickException(
            f"[{AUDIO_CUES_NOT_OPEN}] 当前工作空间尚未开放 audio_cues（schema_version=1），"
            "拒绝提交非空 cue 绑定；未发送任何写入。已保存的历史绑定仍可读取或用 clear 清空。"
        )


def gate_audio_settings_in_payload(
    client: ApiClient,
    payload: Mapping[str, Any],
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
) -> None:
    """通用项目写命令的音频门禁：只拦截显式携带的非空 cue 绑定。"""

    audio_settings = payload.get("audio_settings")
    if not isinstance(audio_settings, Mapping):
        return
    ensure_audio_cues_write_allowed(
        client,
        audio_settings,
        project_id=project_id,
        workspace_id=workspace_id,
    )


def _read_configuration_audio_settings(client: ApiClient, project_id: int) -> dict[str, Any]:
    """读取项目配置中的音频摘要，包含资源逻辑名等只读展示字段。"""

    configuration = client.get(f"/projects/{project_id}/configuration")
    audio_settings = configuration.get("audio_settings") if isinstance(configuration, dict) else None
    if not isinstance(audio_settings, dict):
        raise click.ClickException(
            f"[{AUDIO_CAPABILITY_MISSING}] 当前服务端未返回 audio_settings，请升级服务端后重试。"
        )
    return audio_settings


def _audio_capability_state(client: ApiClient, project_id: int) -> str:
    """终端展示用的能力状态；查询失败只降低可读性，不阻断读取历史值。"""

    try:
        workspace_id = _resolve_workspace_id(client, project_id=project_id)
        capability = load_audio_capability(client, workspace_id)
    except (click.ClickException, ApiClientError):
        return "未知（服务端未声明可识别的音频能力）"
    return "已开放" if capability["audio_cues"] else "未开放（仅可读取或清空现有绑定）"


def _print_audio_settings(project_id: int, audio_settings: dict[str, Any], *, capability: str | None) -> None:
    """以表格展示三段音量与 cue 绑定摘要。"""

    print_success(f"项目音频设置: 项目 {project_id}")
    if capability is not None:
        print_table("能力状态", ["字段", "值"], [["audio_cues", capability]])
    print_table(
        "音量（0–100）",
        ["字段", "值"],
        [
            ["master_volume_percent", str(audio_settings.get("master_volume_percent", "-"))],
            ["narration_volume_percent", str(audio_settings.get("narration_volume_percent", "-"))],
            ["effects_volume_percent", str(audio_settings.get("effects_volume_percent", "-"))],
        ],
    )
    bindings = audio_settings.get("cue_bindings")
    rows = []
    for binding in bindings if isinstance(bindings, list) else []:
        if not isinstance(binding, dict):
            continue
        rows.append(
            [
                str(binding.get("key", "-")),
                str(binding.get("asset_id", "-")),
                str(binding.get("asset_name", "-")),
                str(binding.get("asset_type", "-")),
                str(binding.get("asset_status", "-")),
                str(binding.get("gain_percent", "-")),
            ]
        )
    print_table(
        "cue 绑定",
        ["Cue Key", "资源 ID", "资源逻辑名", "类型", "状态", "Gain%"],
        rows,
    )


@click.group("audio")
def project_audio_group() -> None:
    """项目音量与 cue 绑定；读取保留历史值，写入按 audio_cues 能力门禁。"""


@openapi_command(project_audio_group, "get", contract("GET", "/api/v1/projects/{project_id}/configuration"))
@click.argument("project_id", type=int)
@click.pass_context
def get_project_audio_cmd(ctx: click.Context, project_id: int) -> None:
    """读取项目音频设置；未开放能力时仍返回已保存的历史值。"""

    try:
        client = get_client(ctx)
        audio_settings = _read_configuration_audio_settings(client, project_id)
        if ctx.obj.get("as_json"):
            output_result(ctx, {"project_id": project_id, "audio_settings": audio_settings})
            return
        _print_audio_settings(
            project_id,
            audio_settings,
            capability=_audio_capability_state(client, project_id),
        )
    except ApiClientError as err:
        handle_api_error("读取项目音频设置失败", err)


@openapi_command(
    project_audio_group,
    "update",
    contract("PUT", "/api/v1/projects/{project_id}/configuration"),
    examples=(
        "wp project audio update 130 --audio-file .tmp/web-presentation/audio-130.json --idempotency-key project-130-audio",
    ),
)
@click.argument("project_id", type=int)
@click.option(
    "--audio-file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="完整 audio_settings JSON；可直接提供音频设置对象或包含 audio_settings 字段的对象",
)
@idempotency_key_option
@click.pass_context
def update_project_audio_cmd(ctx: click.Context, project_id: int, audio_file: str) -> None:
    """完整替换项目音量与 cue 绑定；非空 cue 需要 audio_cues 已开放。"""

    try:
        payload = require_object(read_json_file(audio_file, label="音频设置"), label="音频设置")
        raw_settings = payload.get("audio_settings", payload)
        settings = normalize_audio_settings_payload(raw_settings, label="音频设置")
        client = get_client(ctx)
        ensure_audio_cues_write_allowed(client, settings, project_id=project_id)
        client.put(f"/projects/{project_id}/configuration", json_data={"audio_settings": settings})
        audio_settings = _read_configuration_audio_settings(client, project_id)
        if ctx.obj.get("as_json"):
            output_result(ctx, {"project_id": project_id, "audio_settings": audio_settings})
            return
        _print_audio_settings(project_id, audio_settings, capability=None)
    except ApiClientError as err:
        handle_api_error("更新项目音频设置失败", err)


@openapi_command(
    project_audio_group,
    "clear",
    contract("POST", "/api/v1/projects/{project_id}/audio-cues/clear"),
    examples=(
        "wp project audio clear 130 --idempotency-key project-130-audio-clear",
    ),
)
@click.argument("project_id", type=int)
@idempotency_key_option
@click.pass_context
def clear_project_audio_cmd(ctx: click.Context, project_id: int) -> None:
    """清空项目 cue 绑定并保留三段音量；能力关闭时仍可执行。"""

    try:
        result = get_client(ctx).post(f"/projects/{project_id}/audio-cues/clear")
        audio_settings = result.get("audio_settings") if isinstance(result, dict) else None
        if not isinstance(audio_settings, dict):
            raise click.ClickException("清空响应缺少 audio_settings，无法确认结果。")
        if ctx.obj.get("as_json"):
            output_result(ctx, {"project_id": project_id, "audio_settings": audio_settings})
            return
        _print_audio_settings(project_id, audio_settings, capability=None)
    except ApiClientError as err:
        handle_api_error("清空项目 cue 绑定失败", err)


__all__ = [
    "ensure_audio_cues_write_allowed",
    "gate_audio_settings_in_payload",
    "normalize_audio_settings_payload",
    "project_audio_group",
]
