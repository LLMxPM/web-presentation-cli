"""文件功能：测试 CLI 字体与字体族管理子命令（list/get/register/update 与 family list/get/rename）。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wp.cli import main


def test_font_list_cmd_table_and_json() -> None:
    """测试 wp font list 命令的表格与 JSON 输出。"""
    fake_client = MagicMock()
    fake_client.list_fonts.return_value = {
        "items": [
            {
                "id": 1,
                "workspace_id": 1,
                "family_id": 10,
                "family_name": "SourceHanSans",
                "asset_id": 100,
                "asset_name": "source_han.woff2",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
                "created_at": "2026-10-20T10:00:00Z",
                "updated_at": "2026-10-20T10:00:00Z",
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 50,
    }

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        table_res = CliRunner().invoke(main, ["font", "list", "--keyword", "Source"])
        assert table_res.exit_code == 0, table_res.output
        assert "SourceHanSans" in table_res.output
        fake_client.list_fonts.assert_called_with(params={"page": 1, "page_size": 50, "keyword": "Source"})

        json_res = CliRunner().invoke(main, ["--json", "font", "list"])
        assert json_res.exit_code == 0, json_res.output
        data = json.loads(json_res.output)
        assert data["items"][0]["family_name"] == "SourceHanSans"
        assert data["items"][0]["asset_id"] == 100


def test_font_get_cmd_table_and_json() -> None:
    """测试 wp font get 命令的详情输出。"""
    fake_client = MagicMock()
    fake_client.get_font.return_value = {
        "id": 2,
        "workspace_id": 1,
        "family_id": 20,
        "family_name": "CustomSans",
        "asset_id": 102,
        "asset_name": "custom.woff2",
        "font_format": "woff2",
        "font_weight": "700",
        "font_style": "normal",
        "font_display": "swap",
        "status": "active",
        "created_at": "2026-10-20T10:00:00Z",
        "updated_at": "2026-10-20T10:00:00Z",
    }

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        table_res = CliRunner().invoke(main, ["font", "get", "2"])
        json_res = CliRunner().invoke(main, ["--json", "font", "get", "2"])

    assert table_res.exit_code == 0, table_res.output
    assert "CustomSans" in table_res.output
    fake_client.get_font.assert_called_with(2)

    assert json_res.exit_code == 0, json_res.output
    data = json.loads(json_res.output)
    assert data["id"] == 2
    assert data["font_weight"] == "700"


def test_font_register_cmd(tmp_path: Path) -> None:
    """测试 wp font register 读取 payload-file 并调用注册接口。"""
    fake_client = MagicMock()
    fake_client.register_font.return_value = {
        "id": 3,
        "family_id": 30,
        "family_name": "HeadlineFont",
        "asset_id": 105,
        "status": "active",
    }

    payload = {
        "asset_id": 105,
        "family_name": "HeadlineFont",
        "font_weight": "bold",
    }
    payload_file = tmp_path / "register_font.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        res = CliRunner().invoke(
            main,
            [
                "--json",
                "font",
                "register",
                "--payload-file",
                str(payload_file),
                "--idempotency-key",
                "reg-face-1",
            ],
        )

    assert res.exit_code == 0, res.output
    fake_client.register_font.assert_called_once_with(payload)
    data = json.loads(res.output)
    assert data["id"] == 3


def test_font_update_cmd(tmp_path: Path) -> None:
    """测试 wp font update 读取 payload-file 并调用更新接口。"""
    fake_client = MagicMock()
    fake_client.update_font.return_value = {
        "id": 4,
        "family_id": 30,
        "family_name": "HeadlineFontNew",
        "status": "active",
    }

    payload = {"family_name": "HeadlineFontNew"}
    payload_file = tmp_path / "update_font.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        res = CliRunner().invoke(
            main,
            [
                "--json",
                "font",
                "update",
                "4",
                "--payload-file",
                str(payload_file),
                "--idempotency-key",
                "upd-face-1",
            ],
        )

    assert res.exit_code == 0, res.output
    fake_client.update_font.assert_called_once_with(4, payload)
    data = json.loads(res.output)
    assert data["id"] == 4


def test_font_family_list_cmd() -> None:
    """测试 wp font family list 命令的表格与 JSON 输出。"""
    fake_client = MagicMock()
    fake_client.list_font_families.return_value = {
        "items": [
            {
                "id": 10,
                "workspace_id": 1,
                "name": "Inter",
                "faces": [{"id": 1, "font_weight": "400"}, {"id": 2, "font_weight": "700"}],
                "created_at": "2026-10-20T10:00:00Z",
                "updated_at": "2026-10-20T10:00:00Z",
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 50,
    }

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        table_res = CliRunner().invoke(main, ["font", "family", "list", "--keyword", "Inter"])
        assert table_res.exit_code == 0, table_res.output
        assert "Inter" in table_res.output
        fake_client.list_font_families.assert_called_with(params={"page": 1, "page_size": 50, "keyword": "Inter"})

        json_res = CliRunner().invoke(main, ["--json", "font", "family", "list"])
        assert json_res.exit_code == 0, json_res.output
        data = json.loads(json_res.output)
        assert data["items"][0]["name"] == "Inter"
        assert len(data["items"][0]["faces"]) == 2


def test_font_family_get_cmd() -> None:
    """测试 wp font family get 命令的详情输出。"""
    fake_client = MagicMock()
    fake_client.get_font_family.return_value = {
        "id": 10,
        "workspace_id": 1,
        "name": "Roboto",
        "faces": [
            {
                "id": 11,
                "asset_id": 101,
                "asset_name": "roboto.woff2",
                "font_format": "woff2",
                "font_weight": "400",
                "font_style": "normal",
                "font_display": "swap",
                "status": "active",
            }
        ],
        "created_at": "2026-10-20T10:00:00Z",
        "updated_at": "2026-10-20T10:00:00Z",
    }

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        table_res = CliRunner().invoke(main, ["font", "family", "get", "10"])
        json_res = CliRunner().invoke(main, ["--json", "font", "family", "get", "10"])

    assert table_res.exit_code == 0, table_res.output
    assert "Roboto" in table_res.output
    assert "roboto.woff2" in table_res.output
    fake_client.get_font_family.assert_called_with(10)

    assert json_res.exit_code == 0, json_res.output
    data = json.loads(json_res.output)
    assert data["id"] == 10
    assert data["name"] == "Roboto"


def test_font_family_rename_cmd() -> None:
    """测试 wp font family rename 命令。"""
    fake_client = MagicMock()
    fake_client.rename_font_family.return_value = {
        "id": 10,
        "name": "RobotoUpdated",
        "faces": [],
    }

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        res = CliRunner().invoke(
            main,
            [
                "--json",
                "font",
                "family",
                "rename",
                "10",
                "--name",
                "RobotoUpdated",
                "--idempotency-key",
                "ren-1",
            ],
        )

    assert res.exit_code == 0, res.output
    fake_client.rename_font_family.assert_called_once_with(10, "RobotoUpdated")
    data = json.loads(res.output)
    assert data["name"] == "RobotoUpdated"


def test_font_register_rejects_non_object_payload(tmp_path: Path) -> None:
    """测试非法 payload（非对象 JSON，如数组）被正确拦截并返回非零。"""
    bad_file = tmp_path / "bad_array.json"
    bad_file.write_text("[1, 2, 3]", encoding="utf-8")

    res = CliRunner().invoke(main, ["font", "register", "--payload-file", str(bad_file)])
    assert res.exit_code != 0
    assert "必须是 JSON 对象" in res.output
