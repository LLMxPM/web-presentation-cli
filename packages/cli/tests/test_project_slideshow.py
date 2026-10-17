"""文件功能：验证 CLI 放映配置读写与路由整树安全编辑的往返语义。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from click.testing import CliRunner

from wp.cli import main

SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "timer", "delay_ms": 5000},
    "loop": True,
    "auto_start": True,
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


def test_project_slideshow_get_and_update_round_trip(tmp_path: Path) -> None:
    """读取项目默认值并把完整对象写回 PATCH。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {"id": 7, "name": "项目", "slideshow": SLIDESHOW}
    fake_client.patch.return_value = {"id": 7, "slideshow": SLIDESHOW}
    slideshow_file = write_json(tmp_path, "slideshow.json", SLIDESHOW)

    with patch("wp.commands.project.get_client", return_value=fake_client):
        get_result = CliRunner().invoke(main, ["--json", "project", "slideshow", "get", "7"])
        update_result = CliRunner().invoke(
            main, ["--json", "project", "slideshow", "update", "7", "--slideshow-file", str(slideshow_file)]
        )

    assert get_result.exit_code == 0, get_result.output
    assert json.loads(get_result.output)["auto_start"] is True
    assert update_result.exit_code == 0, update_result.output
    fake_client.patch.assert_called_once_with("/projects/7", json_data={"slideshow": SLIDESHOW})


def test_project_slideshow_update_accepts_wrapped_payload(tmp_path: Path) -> None:
    """允许直接复用项目更新载荷中的 slideshow 对象。"""

    fake_client = MagicMock()
    fake_client.patch.return_value = {"slideshow": SLIDESHOW}
    slideshow_file = write_json(tmp_path, "slideshow.json", {"slideshow": SLIDESHOW, "name": "不会发送"})

    with patch("wp.commands.project.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main, ["--json", "project", "slideshow", "update", "7", "--slideshow-file", str(slideshow_file)]
        )

    assert result.exit_code == 0, result.output
    fake_client.patch.assert_called_once_with("/projects/7", json_data={"slideshow": SLIDESHOW})


def test_project_slideshow_reports_old_service_capability_missing(tmp_path: Path) -> None:
    """旧服务缺少 slideshow 字段时不冒充成功。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {"id": 7, "name": "项目"}
    fake_client.patch.return_value = {"id": 7, "name": "项目"}
    slideshow_file = write_json(tmp_path, "slideshow.json", SLIDESHOW)

    with patch("wp.commands.project.get_client", return_value=fake_client):
        get_result = CliRunner().invoke(main, ["--json", "project", "slideshow", "get", "7"])
        update_result = CliRunner().invoke(
            main, ["--json", "project", "slideshow", "update", "7", "--slideshow-file", str(slideshow_file)]
        )

    assert get_result.exit_code != 0 and "SLIDESHOW_CAPABILITY_MISSING" in get_result.output
    assert update_result.exit_code != 0 and "SLIDESHOW_CAPABILITY_MISSING" in update_result.output


def test_project_slideshow_route_help_is_registered() -> None:
    """新命令组与路由编辑命令必须出现在帮助中。"""

    runner = CliRunner()
    slideshow_help = runner.invoke(main, ["project", "slideshow", "--help"])
    route_help = runner.invoke(main, ["project", "route", "update", "--help"])

    assert slideshow_help.exit_code == 0, slideshow_help.output
    assert route_help.exit_code == 0, route_help.output
    assert "update" in slideshow_help.output
    assert "route" in route_help.output
