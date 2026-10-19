"""文件功能：验证项目音频命令的读写模型、能力门禁与原子清空调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from click.testing import CliRunner

from wp.cli import main

AUDIO_SETTINGS = {
    "master_volume_percent": 80,
    "narration_volume_percent": 90,
    "effects_volume_percent": 60,
    "cue_bindings": [
        {"key": "transition.forward", "asset_id": 505, "gain_percent": 75},
    ],
}

CONFIGURATION_AUDIO = {
    **{key: value for key, value in AUDIO_SETTINGS.items() if key != "cue_bindings"},
    "cue_bindings": [
        {
            "key": "transition.forward",
            "asset_id": 505,
            "asset_name": "transition-forward",
            "asset_type": "audio",
            "asset_status": "active",
            "gain_percent": 75,
        }
    ],
}

OPEN_CAPABILITY = {
    "slideshow": {
        "audio": {
            "schema_version": 1,
            "audio_assets": True,
            "page_narration": False,
            "audio_cues": True,
        }
    }
}
CLOSED_CAPABILITY = {
    "slideshow": {
        "audio": {
            "schema_version": 1,
            "audio_assets": True,
            "page_narration": False,
            "audio_cues": False,
        }
    }
}


def write_json(tmp_path: Path, name: str, value: object) -> Path:
    """写入测试 JSON 文件并返回路径。"""

    path = tmp_path / name
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def build_client(*, capability: dict | None, configuration: dict | None = None) -> MagicMock:
    """构造按 URL 返回固定响应的传输替身。"""

    client = MagicMock()
    client.workspace_id = 9
    configuration = configuration or {"project_id": 7, "audio_settings": CONFIGURATION_AUDIO}

    def fake_get(path: str, *args: object, **kwargs: object) -> dict:
        if path == "/projects/7":
            return {"id": 7, "workspace_id": 9}
        if path == "/workspaces/9/capabilities":
            return capability if capability is not None else {}
        if path == "/projects/7/configuration":
            return configuration
        raise AssertionError(f"未预期的 GET: {path}")

    client.get.side_effect = fake_get
    client.put.return_value = {"id": 7, "audio_settings": AUDIO_SETTINGS}
    client.post.return_value = {"id": 7, "audio_settings": {**AUDIO_SETTINGS, "cue_bindings": []}}
    return client


def test_project_audio_get_returns_saved_values() -> None:
    """读取命令只读取配置，不在 JSON 模式追加能力查询。"""

    fake_client = build_client(capability=CLOSED_CAPABILITY)

    with patch("wp.commands.project_audio.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "audio", "get", "7"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["project_id"] == 7
    assert payload["audio_settings"]["cue_bindings"][0]["asset_name"] == "transition-forward"
    fake_client.get.assert_called_once_with("/projects/7/configuration")


def test_project_audio_update_requires_open_capability_for_cues(tmp_path: Path) -> None:
    """能力关闭时拒绝非空 cue 绑定，且不发送写入。"""

    audio_file = write_json(tmp_path, "audio.json", AUDIO_SETTINGS)
    fake_client = build_client(capability=CLOSED_CAPABILITY)

    with patch("wp.commands.project_audio.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "project", "audio", "update", "7", "--audio-file", str(audio_file), "--idempotency-key", "audio-7"],
        )

    assert result.exit_code != 0
    assert "AUDIO_CUES_NOT_OPEN" in result.output
    fake_client.put.assert_not_called()


def test_project_audio_update_writes_complete_settings_and_rereads(tmp_path: Path) -> None:
    """能力开放时只提交 audio_settings，并回读带逻辑名的绑定摘要。"""

    audio_file = write_json(tmp_path, "audio.json", {"audio_settings": AUDIO_SETTINGS})
    fake_client = build_client(capability=OPEN_CAPABILITY)

    with patch("wp.commands.project_audio.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "project", "audio", "update", "7", "--audio-file", str(audio_file), "--idempotency-key", "audio-7"],
        )

    assert result.exit_code == 0, result.output
    fake_client.put.assert_called_once_with(
        "/projects/7/configuration",
        json_data={"audio_settings": AUDIO_SETTINGS},
    )
    payload = json.loads(result.output)
    assert payload["audio_settings"]["cue_bindings"][0]["asset_name"] == "transition-forward"


def test_project_audio_update_rejects_read_only_and_partial_payloads(tmp_path: Path) -> None:
    """读模型字段、缺失音量与 null 必须在本地拒绝，不能悄悄写回。"""

    read_only_file = write_json(tmp_path, "read-only.json", CONFIGURATION_AUDIO)
    partial_file = write_json(tmp_path, "partial.json", {
        "master_volume_percent": 80,
        "cue_bindings": [],
    })
    fake_client = build_client(capability=OPEN_CAPABILITY)

    with patch("wp.commands.project_audio.get_client", return_value=fake_client):
        read_only = CliRunner().invoke(
            main, ["--json", "project", "audio", "update", "7", "--audio-file", str(read_only_file)]
        )
        partial = CliRunner().invoke(
            main, ["--json", "project", "audio", "update", "7", "--audio-file", str(partial_file)]
        )

    assert read_only.exit_code != 0 and "只读字段" in read_only.output
    assert partial.exit_code != 0 and "缺少音量字段" in partial.output
    fake_client.put.assert_not_called()


def test_project_audio_clear_uses_atomic_endpoint() -> None:
    """清空只调用原子接口，不先读后写。"""

    fake_client = build_client(capability=CLOSED_CAPABILITY)

    with patch("wp.commands.project_audio.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "project", "audio", "clear", "7", "--idempotency-key", "audio-clear-7"],
        )

    assert result.exit_code == 0, result.output
    fake_client.post.assert_called_once_with("/projects/7/audio-cues/clear")
    payload = json.loads(result.output)
    assert payload["audio_settings"]["cue_bindings"] == []
    assert payload["audio_settings"]["master_volume_percent"] == 80


def test_generic_project_update_cannot_bypass_capability(tmp_path: Path) -> None:
    """通用项目更新携带非空 cue 时同样受能力门禁保护。"""

    payload_file = write_json(tmp_path, "project.json", {"audio_settings": AUDIO_SETTINGS})
    fake_client = build_client(capability=CLOSED_CAPABILITY)

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "project", "update", "7", "--payload-file", str(payload_file), "--idempotency-key", "project-7"],
        )

    assert result.exit_code != 0
    assert "AUDIO_CUES_NOT_OPEN" in result.output
    fake_client.patch.assert_not_called()


def test_missing_capability_declaration_fails_closed(tmp_path: Path) -> None:
    """服务端未声明可识别音频能力时不得推测支持。"""

    audio_file = write_json(tmp_path, "audio.json", AUDIO_SETTINGS)
    fake_client = build_client(capability=None)

    with patch("wp.commands.project_audio.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main, ["--json", "project", "audio", "update", "7", "--audio-file", str(audio_file)]
        )

    assert result.exit_code != 0
    assert "AUDIO_CAPABILITY_MISSING" in result.output
    fake_client.put.assert_not_called()


def test_project_audio_commands_are_registered() -> None:
    """命令组必须出现在帮助中，便于 Agent 发现。"""

    result = CliRunner().invoke(main, ["project", "audio", "--help"])

    assert result.exit_code == 0, result.output
    for command in ("get", "update", "clear"):
        assert command in result.output
