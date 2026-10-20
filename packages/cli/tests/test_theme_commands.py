"""文件功能：测试 CLI 主题管理命令（包含图片与三槽字体字段的详情展示、完整创建与更新载荷透传）。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wp.cli import main


def test_theme_get_table_displays_design_fields() -> None:
    """测试 wp theme get 表格输出包含品牌Logo、反色Logo、项目图标及三槽字体来源。"""
    fake_client = MagicMock()
    fake_client.get.return_value = {
        "id": 1,
        "key": "corp-theme",
        "name": "企业演示主题",
        "description": "专为企业路演设计",
        "logo_asset_id": 101,
        "logo_asset": {"id": 101, "name": "corp_logo"},
        "invert_logo_asset_id": 102,
        "invert_logo_asset": {"id": 102, "name": "corp_logo_invert"},
        "project_icon_asset_id": 103,
        "project_icon_asset": {"id": 103, "name": "favicon_icon"},
        "heading_font_family_id": 201,
        "heading_font_family": {"id": 201, "name": "CorporateSans"},
        "heading_font_label": "CorporateSans",
        "body_font_preset": "system-ui",
        "body_font_label": "system-ui",
        "code_font_preset": "monospace",
        "code_font_label": "monospace",
    }

    with patch("wp.commands.theme.ApiClient", return_value=fake_client):
        table_res = CliRunner().invoke(main, ["theme", "get", "1"])
        json_res = CliRunner().invoke(main, ["--json", "theme", "get", "1"])

    assert table_res.exit_code == 0, table_res.output
    assert "corp_logo (ID: 101)" in table_res.output
    assert "corp_logo_invert (ID: 102)" in table_res.output
    assert "favicon_icon (ID: 103)" in table_res.output
    assert "族: CorporateSans (ID: 201)" in table_res.output
    assert "预设: system-ui" in table_res.output
    assert "预设: monospace" in table_res.output

    assert json_res.exit_code == 0, json_res.output
    data = json.loads(json_res.output)
    assert data["logo_asset"]["name"] == "corp_logo"
    assert data["heading_font_family"]["name"] == "CorporateSans"


def test_theme_create_with_payload_file(tmp_path: Path) -> None:
    """测试 wp theme create --payload-file 原样转交设计字段。"""
    fake_client = MagicMock()
    fake_client.post.return_value = {
        "id": 5,
        "key": "new-brand",
        "name": "新品牌主题",
        "logo_asset_id": 105,
    }

    payload = {
        "key": "new-brand",
        "name": "新品牌主题",
        "logo_asset_id": 105,
        "heading_font_family_id": 205,
        "body_font_preset": "system-ui",
    }
    payload_file = tmp_path / "create_theme.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        res = CliRunner().invoke(
            main,
            [
                "--json",
                "theme",
                "create",
                "--payload-file",
                str(payload_file),
                "--idempotency-key",
                "create-theme-1",
            ],
        )

    assert res.exit_code == 0, res.output
    fake_client.post.assert_called_once_with("/themes", json_data=payload)
    data = json.loads(res.output)
    assert data["id"] == 5


def test_theme_update_preserves_null_in_payload(tmp_path: Path) -> None:
    """测试 wp theme update --payload-file 显式 null 与省略字段无损透传给服务端。"""
    fake_client = MagicMock()
    fake_client.patch.return_value = {
        "id": 6,
        "key": "corp-brand",
        "name": "已清空Logo主题",
        "logo_asset_id": None,
    }

    payload = {
        "name": "已清空Logo主题",
        "logo_asset_id": None,
        "heading_font_preset": "system-ui",
    }
    payload_file = tmp_path / "update_theme.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        res = CliRunner().invoke(
            main,
            [
                "--json",
                "theme",
                "update",
                "6",
                "--payload-file",
                str(payload_file),
                "--idempotency-key",
                "upd-theme-1",
            ],
        )

    assert res.exit_code == 0, res.output
    fake_client.patch.assert_called_once_with(f"/themes/6", json_data=payload)
    data = json.loads(res.output)
    assert data["id"] == 6
