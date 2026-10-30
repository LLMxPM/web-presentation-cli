"""文件功能：验证 schema 4 放映读写、零完成停留、旧格式拒绝与路由整树安全编辑。"""
from __future__ import annotations

import json

import sys

from pathlib import Path

from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest
from click.testing import CliRunner

from wp.cli import main

SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "timer", "delay_ms": 5000, "completion_delay_ms": 300},
    "loop": True,
}

ROUTE_TREE = {
    "routes": [
        {
            "id": 1,
            "route_type": "page",
            "route": "cover",
            "order": 0,
            "hidden": False,
            "page_id": 11,
            "page_code": "cover-page",
            "page_title": "封面",
            "display_title": "封面",
            "transition": None,
            "advance": None,
            "effective_slideshow": {"transition": SLIDESHOW["transition"], "advance": SLIDESHOW["advance"]},
        },
        {
            "id": 2,
            "route_type": "group",
            "route": "chapter",
            "order": 1,
            "hidden": False,
            "group_title": "第一章",
            "page_id": None,
            "page_code": None,
            "page_title": None,
            "display_title": "第一章",
            "transition": None,
            "advance": None,
            "effective_slideshow": None,
            "children": [
                {
                    "id": 3,
                    "route": "intro",
                    "order": 0,
                    "hidden": False,
                    "page_id": 12,
                    "page_code": "intro-page",
                    "page_title": "导言",
                    "display_title": "导言",
                    "transition": {"effect": "push", "duration_ms": 600},
                    "advance": {"mode": "timer", "delay_ms": 3000},
                    "effective_slideshow": {"transition": {"effect": "push", "duration_ms": 600},
                                            "advance": {"mode": "timer", "delay_ms": 3000}},
                }
            ],
        },
    ]
}

def write_json(tmp_path: Path, name: str, value: object) -> Path:
    """写入测试 JSON 文件并返回路径。"""

    path = tmp_path / name
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path

def test_project_route_update_preserves_overrides_and_filters_read_only(tmp_path: Path) -> None:
    """重排序整树写回应保留原始覆盖并丢弃只读生效值。"""

    edit_file = write_json(tmp_path, "edits.json", [
        {"route": "chapter/intro", "order": 0},
        {"route": "/cover/", "order": 1, "hidden": True},
    ])
    fake_client = MagicMock()
    fake_client.get.return_value = ROUTE_TREE
    fake_client.put.return_value = {"routes": []}

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "route", "update", "7", "--edit-file", str(edit_file)])

    assert result.exit_code == 0, result.output
    fake_client.get.assert_called_once_with("/projects/7/route-tree")
    payload = fake_client.put.call_args.kwargs["json_data"]
    cover, chapter = payload["routes"]
    assert cover == {
        "route_type": "page",
        "route": "cover",
        "order": 1,
        "hidden": True,
        "page_id": 11,
        "transition": None,
        "advance": None,
    }
    assert chapter["route_type"] == "group"
    assert chapter["order"] == 1
    assert chapter["group_title"] == "第一章"
    assert chapter["children"] == [{
        "route": "intro",
        "order": 0,
        "hidden": False,
        "page_id": 12,
        "transition": {"effect": "push", "duration_ms": 600},
        "advance": {"mode": "timer", "delay_ms": 3000},
    }]
    serialized = json.dumps(payload, ensure_ascii=False)
    for read_only in ("effective_slideshow", "page_code", "page_title", "display_title", '"id"'):
        assert read_only not in serialized

def test_project_route_update_sends_explicit_null_to_restore_inheritance(tmp_path: Path) -> None:
    """显式 null 必须进入整树写回载荷，用于清除路由覆盖。"""

    edit_file = write_json(tmp_path, "edits.json", [
        {"route": "chapter/intro", "transition": None, "advance": None},
    ])
    fake_client = MagicMock()
    fake_client.get.return_value = ROUTE_TREE
    fake_client.put.return_value = {"routes": []}

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "route", "update", "7", "--edit-file", str(edit_file)])

    assert result.exit_code == 0, result.output
    child = fake_client.put.call_args.kwargs["json_data"]["routes"][1]["children"][0]
    assert child["transition"] is None
    assert child["advance"] is None

def test_project_route_update_rejects_unknown_route_without_writing(tmp_path: Path) -> None:
    """未知路由不能生成部分写回。"""

    edit_file = write_json(tmp_path, "edits.json", [{"route": "missing", "order": 0}])
    fake_client = MagicMock()
    fake_client.get.return_value = ROUTE_TREE

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "route", "update", "7", "--edit-file", str(edit_file)])

    assert result.exit_code != 0
    assert "路由不存在" in result.output
    fake_client.put.assert_not_called()

def test_project_route_update_reports_old_service_capability_missing(tmp_path: Path) -> None:
    """旧服务缺少放映字段时明确报能力缺失，不猜测写回。"""

    legacy_tree = {
        "routes": [{
            "id": 1, "route_type": "page", "route": "cover", "order": 0, "hidden": False,
            "page_id": 11, "page_code": "cover-page", "page_title": "封面", "display_title": "封面",
        }]
    }
    edit_file = write_json(tmp_path, "edits.json", [{"route": "cover", "order": 1}])
    fake_client = MagicMock()
    fake_client.get.return_value = legacy_tree

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "route", "update", "7", "--edit-file", str(edit_file)])

    assert result.exit_code != 0
    assert "SLIDESHOW_CAPABILITY_MISSING" in result.output
    fake_client.put.assert_not_called()

def test_project_slideshow_route_help_is_registered() -> None:
    """新命令组与路由编辑命令必须出现在帮助中。"""

    runner = CliRunner()
    slideshow_help = runner.invoke(main, ["project", "slideshow", "--help"])
    route_help = runner.invoke(main, ["project", "route", "update", "--help"])

    assert slideshow_help.exit_code == 0, slideshow_help.output
    assert route_help.exit_code == 0, route_help.output
    assert "update" in slideshow_help.output
    assert "route" in route_help.output

def test_project_slideshow_rejects_unknown_advance_mode(tmp_path: Path) -> None:
    """未知模式明确失败，不静默改成 timer。"""

    fake_client = MagicMock()
    slideshow_file = write_json(tmp_path, "slideshow.json", {
        **SLIDESHOW,
        "advance": {"mode": "video_done", "delay_ms": 5000},
    })

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main, ["--json", "project", "slideshow", "update", "7", "--slideshow-file", str(slideshow_file)]
        )

    assert result.exit_code != 0
    assert "SLIDESHOW_ADVANCE_MODE_UNKNOWN" in result.output
    fake_client.get.assert_not_called()
    fake_client.patch.assert_not_called()

def test_project_route_update_rejects_unknown_advance_before_writing(tmp_path: Path) -> None:
    """路由覆盖使用未知模式时整树不写回。"""

    fake_client = MagicMock()
    fake_client.get.return_value = ROUTE_TREE
    edit_file = write_json(tmp_path, "edits.json", [{"route": "cover", "advance": {"mode": "auto", "delay_ms": 5000}}])

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "route", "update", "7", "--edit-file", str(edit_file)])

    assert result.exit_code != 0
    assert "SLIDESHOW_ADVANCE_MODE_UNKNOWN" in result.output
    fake_client.put.assert_not_called()

@pytest.mark.parametrize("mode", ["manual", "timer", "scene_end"])
def test_scene_slideshow_round_trip(tmp_path: Path, mode: str) -> None:
    """三模式使用同一 schema 4，完成停留零必须原样写入。"""
    value = {**SLIDESHOW, "advance": {"mode": mode, "delay_ms": 5000, "completion_delay_ms": 0}}
    file = write_json(tmp_path, "slideshow.json", {"slideshow": value})
    client = MagicMock()
    client.get.side_effect = [{"workspace_id": 9}, {"slideshow": {"schema_version": 4, "advance_modes": ["manual", "timer", "scene_end"]}}]
    client.patch.return_value = {"slideshow": value}
    with patch("wp.commands.project.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "project", "slideshow", "update", "7", "--slideshow-file", str(file)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == value
    client.patch.assert_called_once_with("/projects/7", json_data={"slideshow": value})

@pytest.mark.parametrize("capability", [{}, {"schema_version": 3, "advance_modes": ["manual", "timer"]}, {"schema_version": 4, "advance_modes": ["manual", "timer"]}])
def test_missing_scene_schema_is_rejected_before_write(tmp_path: Path, capability: dict) -> None:
    """旧版本或缺失声明不能把 scene_end 静默降为 timer。"""
    client = MagicMock(); client.get.side_effect = [{"workspace_id": 9}, {"slideshow": capability}]
    file = write_json(tmp_path, "slideshow.json", SLIDESHOW)
    with patch("wp.commands.project.get_client", return_value=client):
        result = CliRunner().invoke(main, ["project", "slideshow", "update", "7", "--slideshow-file", str(file)])
    assert result.exit_code != 0 and "SLIDESHOW_CAPABILITY_MISSING" in result.output
    client.patch.assert_not_called()

@pytest.mark.parametrize("advance", [
    {"mode": "media_end", "delay_ms": 5000}, {"mode": "timeline_end", "delay_ms": 5000},
    {"mode": "scene_end", "delay_ms": 5000, "media_timeout_ms": 1000},
    {"mode": "scene_end", "delay_ms": 5000, "timeline_timeout_ms": 1000},
    {"mode": "scene_end", "delay_ms": 5000, "completion_delay_ms": -1},
    {"mode": "scene_end", "delay_ms": 5000, "completion_delay_ms": True},
])
def test_legacy_or_invalid_advance_is_rejected_locally(tmp_path: Path, advance: dict) -> None:
    """旧字段与非法整数在读取能力或写入前拒绝。"""
    client = MagicMock(); file = write_json(tmp_path, "slideshow.json", {**SLIDESHOW, "advance": advance})
    with patch("wp.commands.project.get_client", return_value=client):
        result = CliRunner().invoke(main, ["project", "slideshow", "update", "7", "--slideshow-file", str(file)])
    assert result.exit_code != 0 and "SLIDESHOW_ADVANCE_MODE_UNKNOWN" in result.output
    client.get.assert_not_called(); client.patch.assert_not_called()
