"""文件功能：验证首版 CLI 新增资源命令、文件载荷和复杂参数入口。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from click.testing import CliRunner

from wp.cli import main


def test_new_command_groups_are_registered() -> None:
    """顶层和资源级能力分组应全部出现在帮助中。"""

    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for command in ("system", "standards", "runtime-kit", "font", "job"):
        assert command in result.output

    for args in (
        ["project", "configuration", "--help"],
        ["project", "route", "--help"],
        ["page", "version", "--help"],
        ["component", "version", "--help"],
        ["asset", "content", "--help"],
        ["asset", "tags", "--help"],
        ["asset", "replace", "--help"],
        ["asset", "download", "--help"],
    ):
        nested = CliRunner().invoke(main, args)
        assert nested.exit_code == 0, (args, nested.output)


def test_project_update_reads_json_payload(tmp_path: Path) -> None:
    """项目更新应把 JSON 文件原样传给 External API。"""

    payload_file = tmp_path / "project.json"
    payload = {"name": "新项目", "description": "首版测试"}
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    fake_client = MagicMock()
    fake_client.patch.return_value = {"id": 7, "name": "新项目"}
    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "update", "7", "--payload-file", str(payload_file)])

    assert result.exit_code == 0, result.output
    fake_client.patch.assert_called_once_with("/projects/7", json_data=payload)
    assert '"id": 7' in result.output


def test_style_create_reads_flat_full_payload(tmp_path: Path) -> None:
    """样式创建应把包含完整顶层展示字段的 JSON 载荷传给 External API。"""

    payload_file = tmp_path / "style.json"
    payload = {
        "key": "flat-style",
        "name": "完整样式",
        "description": "CLI 测试",
        "page_width": 1920,
        "page_height": 1080,
        "base_font_size": "18px",
        "icon_default_stroke_width": 3,
        "show_pdf_export_button": False,
        "menu_mode": "bottom-preview",
        "theme_key": None,
        "style_spec_markdown": "## 规范",
    }
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    fake_client = MagicMock()
    fake_client.post.return_value = {"id": 13, "key": "flat-style"}
    with patch("wp.commands.style.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "style", "create", "--payload-file", str(payload_file)],
        )

    assert result.exit_code == 0, result.output
    fake_client.post.assert_called_once_with("/styles", json_data=payload)


def test_style_create_help_describes_full_payload_fields() -> None:
    """样式创建帮助应说明完整 payload 支持的字段形态。"""

    result = CliRunner().invoke(main, ["style", "create", "--help"])

    assert result.exit_code == 0, result.output
    assert "configuration.presentation" in result.output
    assert "page_width" in result.output


def test_asset_list_accepts_model3d_and_projects_summary() -> None:
    """资源列表应接受 model3d 类型并输出模型选择摘要。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {
        "items": [
            {
                "id": 42,
                "name": "product",
                "asset_type": "model3d",
                "render_type": "model3d",
                "analysis_metadata": {
                    "kind": "model3d",
                    "model3d": {"format": "glb", "scene_count": 1, "cameras": [], "animations": []},
                },
            }
        ],
        "page": 1,
        "page_size": 50,
        "total": 1,
    }
    with patch("wp.commands.asset.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "asset", "list", "--type", "model3d"])

    assert result.exit_code == 0, result.output
    fake_client.get.assert_called_once_with("/assets", params={"page": 1, "page_size": 50, "asset_type": "model3d"})
    payload = json.loads(result.output)
    assert payload["items"][0]["model3d"] == {
        "format": "glb",
        "scene_count": 1,
        "camera_count": 0,
        "animation_count": 0,
    }


def test_asset_replace_sends_expected_hash_and_idempotency_key(tmp_path: Path) -> None:
    """资源替换应携带版本基线和命令级幂等键。"""

    model_file = tmp_path / "product-v2.glb"
    model_file.write_bytes(b"glTF\x02\x00\x00\x00")
    fake_client = MagicMock()
    fake_client.upload.return_value = {"id": 42, "name": "product", "asset_type": "model3d"}
    captured: dict[str, str | None] = {}

    def fake_get_client(ctx: object) -> MagicMock:
        """捕获命令写入上下文的幂等键，并返回传输替身。"""

        captured["idempotency_key"] = ctx.obj.get("idempotency_key")  # type: ignore[attr-defined]
        return fake_client

    with patch("wp.commands.asset.get_client", side_effect=fake_get_client):
        result = CliRunner().invoke(
            main,
            [
                "--json",
                "asset",
                "replace",
                "42",
                str(model_file),
                "--expected-file-hash",
                "abc123",
                "--idempotency-key",
                "asset-product-replace",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["idempotency_key"] == "asset-product-replace"
    fake_client.upload.assert_called_once()
    call = fake_client.upload.call_args
    assert call.args[0] == "/assets/42/replace"
    assert call.kwargs["data"] == {"expected_file_hash": "abc123"}
    assert call.kwargs["files"]["file"][0] == "product-v2.glb"
    assert json.loads(result.output)["id"] == 42


def test_asset_download_writes_original_binary(tmp_path: Path) -> None:
    """资源下载应使用详情中的名称与当前 hash 保存原始文件。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {
        "id": 42,
        "name": "product",
        "original_name": "product.glb",
        "asset_type": "model3d",
        "file_hash": "abc123",
    }
    fake_client.get_bytes.return_value = ({"etag": "abc123"}, b"glTF-binary")
    save_path = tmp_path / "downloads" / "product.glb"

    with patch("wp.commands.asset.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "asset", "download", "42", "--output", str(save_path)],
        )

    assert result.exit_code == 0, result.output
    assert save_path.read_bytes() == b"glTF-binary"
    fake_client.get_bytes.assert_called_once_with(
        "/assets/42/file",
        params={"download": 1, "hash": "abc123"},
    )
    payload = json.loads(result.output)
    assert payload["saved_file"] == str(save_path.resolve())
    assert payload["file_hash"] == "abc123"
    assert payload["size_bytes"] == len(b"glTF-binary")


def test_asset_content_update_reads_raw_text(tmp_path: Path) -> None:
    """资源内容更新应保持 UTF-8 文本原样，不把内容当 JSON 解析。"""

    content_file = tmp_path / "diagram.mmd"
    content = "graph TD\n  A-->B\n"
    content_file.write_text(content, encoding="utf-8")
    fake_client = MagicMock()
    fake_client.put.return_value = {"id": 3}
    with patch("wp.commands.asset.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "asset", "content", "update", "3", "--content-file", str(content_file)])

    assert result.exit_code == 0, result.output
    fake_client.put.assert_called_once_with(
        "/assets/3/content",
        json_data={"content": content, "change_note": None},
    )


def test_archive_ids_file_rejects_non_integer_ids(tmp_path: Path) -> None:
    """批量归档文件必须是正整数数组。"""

    ids_file = tmp_path / "ids.json"
    ids_file.write_text(json.dumps([1, "two"]), encoding="utf-8")
    result = CliRunner().invoke(main, ["project", "archive", "--ids-file", str(ids_file), "--yes"])

    assert result.exit_code != 0
    assert "正整数" in result.output


def test_asset_upload_audio_sends_audio_type_and_content_type(tmp_path: Path) -> None:
    """音频上传必须使用 audio 类型并显式声明受支持的 Content-Type。"""

    audio_file = tmp_path / "transition-forward.mp3"
    audio_file.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00")
    fake_client = MagicMock()
    fake_client.upload.return_value = {"id": 505, "name": "transition-forward", "asset_type": "audio"}

    with patch("wp.commands.asset.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            [
                "--json",
                "asset",
                "upload",
                str(audio_file),
                "--type",
                "audio",
                "--name",
                "transition-forward",
                "--idempotency-key",
                "asset-transition-forward",
            ],
        )

    assert result.exit_code == 0, result.output
    call = fake_client.upload.call_args
    assert call.args[0] == "/assets"
    assert call.kwargs["data"] == {
        "asset_type": "audio",
        "name": "transition-forward",
        "description": None,
    }
    name, _file_obj, content_type = call.kwargs["files"]["file"]
    assert name == "transition-forward.mp3"
    assert content_type == "audio/mpeg"


def test_asset_list_and_tags_accept_audio_type() -> None:
    """audio 类型必须同时覆盖资源列表过滤与标签查询，而不只是上传。"""

    fake_client = MagicMock()
    fake_client.get.side_effect = [
        {"items": [], "page": 1, "page_size": 50, "total": 0},
        {"items": []},
    ]

    with patch("wp.commands.asset.get_client", return_value=fake_client):
        list_result = CliRunner().invoke(main, ["--json", "asset", "list", "--type", "audio"])
        tags_result = CliRunner().invoke(main, ["--json", "asset", "tags", "list", "--type", "audio"])

    assert list_result.exit_code == 0, list_result.output
    assert tags_result.exit_code == 0, tags_result.output
    fake_client.get.assert_any_call(
        "/assets",
        params={"page": 1, "page_size": 50, "asset_type": "audio"},
    )
    fake_client.get.assert_any_call("/assets/tags", params={"asset_type": "audio"})
