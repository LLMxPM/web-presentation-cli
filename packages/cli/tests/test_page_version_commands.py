"""文件功能：测试页面版本列表、导出、比较、重点快照命令与历史版本预览分支。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wp.cli import main

_VERSIONS = [
    {
        "id": 12,
        "version_no": 3,
        "version_label": "20261102-131500",
        "is_current": True,
        "is_important": False,
        "snapshot_name": None,
        "change_note": "第三版",
        "storage_type": "snapshot",
        "created_at": "2026-11-02T05:15:00Z",
        "created_by": 1,
    },
    {
        "id": 8,
        "version_no": 2,
        "version_label": "V1.1",
        "is_current": False,
        "is_important": True,
        "snapshot_name": "内容确认版",
        "change_note": "第二版",
        "storage_type": "snapshot",
        "created_at": "2026-11-02T05:10:00Z",
        "created_by": 1,
    },
    {
        "id": 3,
        "version_no": 1,
        "version_label": "V1",
        "is_current": False,
        "is_important": True,
        "snapshot_name": "初版",
        "change_note": "初始版本",
        "storage_type": "diff",
        "created_at": "2026-11-02T05:05:00Z",
        "created_by": 1,
    },
]


def _detail(version_no: int, *, content: str, notes: str | None) -> dict:
    """构造版本详情响应，保留 resolved_content 与备注。"""

    return {
        "page_id": 21,
        "version_no": version_no,
        "version_label": f"v{version_no}",
        "file_type": "vue",
        "storage_type": "snapshot",
        "is_important": False,
        "snapshot_name": None,
        "change_note": None,
        "speaker_notes": notes,
        "content_mode": "full",
        "content": content,
        "resolved_content": content,
        "created_at": "2026-11-02T05:05:00Z",
        "created_by": 1,
    }


def test_version_list_filters_important_before_limit() -> None:
    """--important 先在完整列表上筛选，--limit 再限制数量。"""

    client = MagicMock()
    client.get.return_value = _VERSIONS

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "page", "version", "list", "21", "--important", "--limit", "1"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [item["version_no"] for item in payload] == [2]
    client.get.assert_called_once_with("/pages/21/versions")


def test_version_list_json_keeps_array_shape() -> None:
    """--json 继续返回顶层数组，不改为分页 envelope。"""

    client = MagicMock()
    client.get.return_value = _VERSIONS

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "page", "version", "list", "21"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [item["version_no"] for item in payload] == [3, 2, 1]


def test_version_list_plain_output_uses_table_columns() -> None:
    """普通终端输出使用表格，覆盖版本号、标签、当前标记、快照名、说明、时间和创建者。"""

    client = MagicMock()
    client.get.return_value = _VERSIONS

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["page", "version", "list", "21"])

    assert result.exit_code == 0, result.output
    for header in ("版本", "标签", "当前", "快照名", "修改说明", "创建时间", "创建者"):
        assert header in result.output
    assert "内容确认版" in result.output


def test_version_list_rejects_non_array_response() -> None:
    """版本列表响应不是数组时明确失败，不做隐式兼容。"""

    client = MagicMock()
    client.get.return_value = {"items": _VERSIONS}

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["page", "version", "list", "21"])

    assert result.exit_code != 0
    assert "必须是数组" in result.output


def test_version_list_rejects_non_object_items() -> None:
    """数组中出现非对象项时按契约异常失败，不得静默丢弃导致历史不完整。"""

    client = MagicMock()
    client.get.return_value = [_VERSIONS[0], None, "corrupted"]

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "page", "version", "list", "21"])

    assert result.exit_code != 0
    assert "不是 JSON 对象" in result.output


def test_version_export_writes_resolved_content_verbatim(tmp_path: Path) -> None:
    """导出写入 resolved_content 原文，保留中文、无末尾换行，并报告 UTF-8 字节数。"""

    content = "<template><div>中文内容</div></template>"
    client = MagicMock()
    client.get.return_value = _detail(5, content=content, notes="备注")

    target = tmp_path / "nested" / "page-21-v5.vue"
    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(
            main,
            ["--json", "page", "version", "export", "21", "5", "--output", str(target)],
        )

    assert result.exit_code == 0, result.output
    assert target.read_bytes() == content.encode("utf-8")
    payload = json.loads(result.output)
    assert payload == {
        "page_id": 21,
        "version_no": 5,
        "file_type": "vue",
        "output_path": str(target.resolve()),
        "bytes": len(content.encode("utf-8")),
    }


def test_version_export_refuses_overwrite_without_flag(tmp_path: Path) -> None:
    """默认拒绝覆盖既有文件，显式 --overwrite 才允许写入。"""

    target = tmp_path / "page-21-v5.vue"
    target.write_text("已有内容", encoding="utf-8")
    client = MagicMock()
    client.get.return_value = _detail(5, content="新内容", notes=None)

    with patch("wp.commands.page_version.get_client", return_value=client):
        blocked = CliRunner().invoke(
            main, ["page", "version", "export", "21", "5", "--output", str(target)]
        )
    assert blocked.exit_code != 0
    assert "--overwrite" in blocked.output
    assert target.read_text(encoding="utf-8") == "已有内容"

    with patch("wp.commands.page_version.get_client", return_value=client):
        allowed = CliRunner().invoke(
            main, ["page", "version", "export", "21", "5", "--output", str(target), "--overwrite"]
        )
    assert allowed.exit_code == 0, allowed.output
    assert target.read_text(encoding="utf-8") == "新内容"


def test_version_export_requires_resolved_content() -> None:
    """缺少 resolved_content 时不得把差异文本当源码导出。"""

    client = MagicMock()
    detail = _detail(5, content="差异", notes=None)
    detail.pop("resolved_content")
    client.get.return_value = detail

    with patch("wp.commands.page_version.get_client", return_value=client), patch(
        "wp.commands.page_version.Path.write_text"
    ) as write_text:
        result = CliRunner().invoke(
            main, ["page", "version", "export", "21", "5", "--output", "out.vue"]
        )

    assert result.exit_code != 0
    assert "resolved_content" in result.output
    write_text.assert_not_called()


def test_version_diff_reports_notes_only_change_and_exit_zero() -> None:
    """仅备注变化时源码无差异、备注有差异，且命令以 0 退出。"""

    client = MagicMock()
    client.get.side_effect = [
        _detail(5, content="<template><div>同一份</div></template>", notes="旧备注"),
        _detail(12, content="<template><div>同一份</div></template>", notes="新备注"),
    ]

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "page", "version", "diff", "21", "5", "12"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["changed"] is True
    assert payload["changed_fields"] == ["speaker_notes"]
    assert payload["comparisons"]["source"]["changed"] is False
    assert "旧备注" in payload["comparisons"]["speaker_notes"]["diff"]
    assert "新备注" in payload["comparisons"]["speaker_notes"]["diff"]


def test_version_diff_treats_null_and_empty_notes_as_change() -> None:
    """备注的 null 与空串语义不同，diff 文本相同也必须报变更。"""

    client = MagicMock()
    client.get.side_effect = [
        _detail(5, content="<template />", notes=None),
        _detail(6, content="<template />", notes=""),
    ]

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(
            main, ["--json", "page", "version", "diff", "21", "5", "6", "--field", "speaker_notes"]
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["changed"] is True
    assert payload["comparisons"]["speaker_notes"]["changed"] is True
    assert payload["comparisons"]["speaker_notes"]["diff"] == ""


def test_version_diff_same_version_reads_once_and_reports_no_change() -> None:
    """相同版本只读取一次，并以成功状态报告无差异。"""

    client = MagicMock()
    client.get.return_value = _detail(5, content="<template />", notes="备注")

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "page", "version", "diff", "21", "5", "5"])

    assert result.exit_code == 0, result.output
    assert client.get.call_count == 1
    assert json.loads(result.output)["changed"] is False


def test_version_diff_plain_output_prints_unified_diff() -> None:
    """普通输出为分字段 unified diff，带 from → to 方向。"""

    client = MagicMock()
    client.get.side_effect = [
        _detail(5, content="<template><div>旧</div></template>\n", notes=None),
        _detail(12, content="<template><div>新</div></template>\n", notes=None),
    ]

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["page", "version", "diff", "21", "5", "12"])

    assert result.exit_code == 0, result.output
    assert "-<template><div>旧</div></template>" in result.output
    assert "+<template><div>新</div></template>" in result.output


def test_version_diff_api_failure_does_not_report_success() -> None:
    """读取失败时不得输出成功比较结果。"""

    from wp.client import ApiClientError

    client = MagicMock()
    client.get.side_effect = ApiClientError("页面版本不存在。", status_code=404, code="PAGE_VERSION_NOT_FOUND")

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "page", "version", "diff", "21", "5", "12"])

    assert result.exit_code != 0
    assert "PAGE_VERSION_NOT_FOUND" in result.output


def test_version_snapshot_sends_trimmed_name() -> None:
    """快照命令提交去空白后的名称，并输出标记结果。"""

    client = MagicMock()
    client.create_page_version_snapshot.return_value = {
        "page_id": 21,
        "version_no": 12,
        "version_label": "V2",
        "snapshot_name": "内容确认版",
        "is_important": True,
    }

    with patch("wp.commands.page_version.get_client", return_value=client):
        result = CliRunner().invoke(
            main, ["page", "version", "snapshot", "21", "12", "--name", "  内容确认版  "]
        )

    assert result.exit_code == 0, result.output
    client.create_page_version_snapshot.assert_called_once_with(21, 12, snapshot_name="内容确认版")
    assert "内容确认版" in result.output


def test_version_snapshot_rejects_empty_and_too_long_names() -> None:
    """名称必须非空且不超过 128 字符，参数错误在发请求前发生。"""

    client = MagicMock()
    with patch("wp.commands.page_version.get_client", return_value=client):
        empty = CliRunner().invoke(main, ["page", "version", "snapshot", "21", "12", "--name", "   "])
        too_long = CliRunner().invoke(main, ["page", "version", "snapshot", "21", "12", "--name", "名" * 129])

    assert empty.exit_code != 0
    assert too_long.exit_code != 0
    client.create_page_version_snapshot.assert_not_called()


def test_version_commands_require_positive_integers() -> None:
    """页面 ID、版本号与 --limit 都必须是正整数。"""

    for args in (
        ["page", "version", "list", "0"],
        ["page", "version", "list", "21", "--limit", "0"],
        ["page", "version", "get", "21", "0"],
    ):
        result = CliRunner().invoke(main, args)
        assert result.exit_code != 0, args


def test_preview_with_version_uses_history_branch() -> None:
    """--version 走历史版本预览分支，输出保留目标页面与版本。"""

    client = MagicMock()
    client.create_page_version_preview_artifact.return_value = {
        "preview_url": "https://example.test/version-preview",
        "artifact_id": "artifact-v5",
        "preview_kind": "page",
        "entry_descriptor": {"entry_type": "module", "module_path": "src/views/page.vue"},
        "viewport_width": 1920,
        "viewport_height": 1080,
        "expires_at": "2026-11-02T06:00:00Z",
    }

    with patch("wp.commands.preview.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "preview", "get", "--page-id", "21", "--version", "5"])

    assert result.exit_code == 0, result.output
    client.create_page_version_preview_artifact.assert_called_once_with(21, 5)
    payload = json.loads(result.output)
    assert payload["page_id"] == 21
    assert payload["version_no"] == 5
    assert payload["expires_at"] == "2026-11-02T06:00:00Z"


def test_preview_version_raw_output_keeps_backend_response_verbatim() -> None:
    """--raw 输出 Backend 原始响应，不注入 CLI 合成的 page_id/version_no 字段。"""

    backend_response = {
        "preview_url": "https://example.test/version-preview",
        "artifact_id": "artifact-v5",
        "preview_kind": "page",
        "entry_descriptor": {"entry_type": "module", "module_path": "src/views/page.vue"},
        "viewport_width": 1920,
        "viewport_height": 1080,
        "expires_at": "2026-11-02T06:00:00Z",
    }
    client = MagicMock()
    client.create_page_version_preview_artifact.return_value = dict(backend_response)

    with patch("wp.commands.preview.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--raw", "preview", "get", "--page-id", "21", "--version", "5"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == backend_response


def test_preview_version_requires_page_target() -> None:
    """--version 不能与项目目标或 --route 混用，参数错误在发请求前报出。"""

    client = MagicMock()
    with patch("wp.commands.preview.get_client", return_value=client):
        project_target = CliRunner().invoke(main, ["preview", "get", "--project-id", "7", "--version", "5"])
        with_route = CliRunner().invoke(
            main, ["preview", "get", "--page-id", "21", "--version", "5", "--route", "overview"]
        )
        missing_page = CliRunner().invoke(main, ["preview", "get", "--version", "5"])

    for result in (project_target, with_route, missing_page):
        assert result.exit_code != 0
    client.create_page_version_preview_artifact.assert_not_called()
    client.create_preview_artifact.assert_not_called()
