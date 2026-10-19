"""文件功能：验证 CLI 精简 JSON、原始 JSON 和资源返回字段投影。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wp.cli import main
from wp.output_profiles import project_response


def test_project_projection_keeps_user_names_and_page_counts() -> None:
    """项目摘要必须保留用户交互名称和整体页面统计。"""

    result = project_response(
        {
            "items": [
                {
                    "id": 7,
                    "workspace_id": 1,
                    "workspace_name": "演示空间",
                    "name": "季度复盘",
                    "routed_page_count": 4,
                    "total_page_count": 5,
                    "page_width": 1600,
                    "internal_debug": "drop",
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 1,
        },
        "project_list",
    )

    item = result["items"][0]
    assert item["workspace_name"] == "演示空间"
    assert item["routed_page_count"] == 4
    assert item["total_page_count"] == 5
    assert "page_width" not in item
    assert "internal_debug" not in item


def test_page_and_component_projections_hide_source_content() -> None:
    """页面元数据和组件列表不应默认携带完整源码。"""

    page = project_response(
        {"id": 3, "workspace_name": "空间", "project_name": "项目", "page_content": "<template />"},
        "page_detail",
    )
    component = project_response(
        {"items": [{"id": 4, "name": "卡片", "content": "<template />", "preview_schema": "{}"}]},
        "component_list",
    )

    assert page["workspace_name"] == "空间"
    assert page["project_name"] == "项目"
    assert "page_content" not in page
    assert "content" not in component["items"][0]
    assert "preview_schema" not in component["items"][0]


def test_asset_list_projects_model3d_summary_without_full_analysis() -> None:
    """资源列表应给出三维选择摘要，并继续隐藏完整分析元数据。"""

    result = project_response(
        {
            "items": [
                {
                    "id": 42,
                    "name": "product",
                    "asset_type": "model3d",
                    "analysis_metadata": {
                        "kind": "model3d",
                        "model3d": {
                            "format": "glb",
                            "scene_count": 2,
                            "cameras": [{"index": 0}, {"index": 1}],
                            "animations": [{"index": 0}],
                            "warnings": ["示例 warning"],
                        },
                    },
                    "internal_debug": "drop",
                },
                {
                    "id": 43,
                    "name": "hero",
                    "asset_type": "image",
                    "analysis_metadata": {"kind": "icon", "icon": {"width": 32}},
                },
            ],
            "page": 1,
            "page_size": 50,
            "total": 2,
        },
        "asset_list",
    )

    model_item, image_item = result["items"]
    assert model_item["model3d"] == {
        "format": "glb",
        "scene_count": 2,
        "camera_count": 2,
        "animation_count": 1,
    }
    assert "analysis_metadata" not in model_item
    assert "internal_debug" not in model_item
    assert "model3d" not in image_item


def test_theme_validation_and_archive_projections_follow_profiles() -> None:
    """主题嵌套详情保留，诊断和批量归档字段按场景收敛。"""

    theme = project_response(
        {"id": 1, "logo_asset": {"id": 8}, "body_font_family": {"id": 9}, "extra": "drop"},
        "theme",
    )
    validation = project_response(
        {
            "entity_type": "page",
            "valid": True,
            "summary": "通过",
            "diagnostics": [{"code": "ok"}],
        },
        "validation",
    )
    detailed_validation = project_response(
        {
            "entity_type": "page",
            "valid": True,
            "summary": "通过",
            "diagnostics": [{"code": "ok"}],
        },
        "validation",
        detail=True,
    )
    archive = project_response({"archived_ids": [1, 2], "failed_ids": [], "total": 2}, "archive")

    assert theme["logo_asset"] == {"id": 8}
    assert theme["body_font_family"] == {"id": 9}
    assert "extra" not in theme
    assert "diagnostics" not in validation
    assert detailed_validation["diagnostics"] == [{"code": "ok"}]
    assert archive == {"archived_ids": [1, 2], "total": 2}


def test_raw_project_list_bypasses_projection() -> None:
    """--raw 应保留 Backend 返回的精简投影之外字段。"""

    client = MagicMock()
    client.get.return_value = {
        "items": [{"id": 7, "workspace_name": "空间", "internal_debug": "keep-in-raw"}],
        "total": 1,
    }

    with patch("wp.commands.project.ApiClient", return_value=client):
        compact = CliRunner().invoke(main, ["--json", "project", "list"])
        raw = CliRunner().invoke(main, ["--raw", "project", "list"])

    assert compact.exit_code == 0, compact.output
    assert raw.exit_code == 0, raw.output
    assert "internal_debug" not in json.loads(compact.output)["items"][0]
    assert json.loads(raw.output)["items"][0]["internal_debug"] == "keep-in-raw"


def test_json_and_raw_are_mutually_exclusive() -> None:
    """两种机器输出模式不能同时指定。"""

    result = CliRunner().invoke(main, ["--json", "--raw", "project", "list"])

    assert result.exit_code != 0
    assert "不能同时使用" in result.output


def test_component_projection_includes_import_usage() -> None:
    """组件列表和详情投影中必须保留 import_path 和 import_statement。"""

    component_list = project_response(
        {
            "items": [
                {
                    "id": 4,
                    "code": "CMP001",
                    "name": "卡片",
                    "import_name": "MyCard",
                    "current_version_no": 1,
                    "import_path": "@workspace-components/CMP001/v/1",
                    "import_statement": "import MyCard from '@workspace-components/CMP001/v/1'",
                    "content": "<template />",
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 1,
        },
        "component_list",
    )
    assert component_list["items"][0]["import_path"] == "@workspace-components/CMP001/v/1"
    assert component_list["items"][0]["import_statement"] == "import MyCard from '@workspace-components/CMP001/v/1'"
    assert "content" not in component_list["items"][0]

    component_detail = project_response(
        {
            "id": 4,
            "code": "CMP001",
            "name": "卡片",
            "import_name": "MyCard",
            "current_version_no": 1,
            "import_path": "@workspace-components/CMP001/v/1",
            "import_statement": "import MyCard from '@workspace-components/CMP001/v/1'",
            "content": "<template />",
            "preview_schema": "{}",
            "draft_hash": "hash123",
        },
        "component_detail",
    )
    assert component_detail["import_path"] == "@workspace-components/CMP001/v/1"
    assert component_detail["import_statement"] == "import MyCard from '@workspace-components/CMP001/v/1'"


def test_project_detail_keeps_audio_settings_and_slideshow_only_when_present() -> None:
    """项目详情应保留服务端音频与放映字段；旧响应缺字段时不补 null。"""

    audio_settings = {
        "master_volume_percent": 80,
        "narration_volume_percent": 100,
        "effects_volume_percent": 60,
        "cue_bindings": [
            {
                "key": "transition.forward",
                "asset_id": 505,
                "asset_name": "transition-forward",
                "asset_type": "audio",
                "asset_status": "active",
                "gain_percent": 90,
            }
        ],
    }
    slideshow = {"transition": {"effect": "fade", "duration_ms": 400}, "advance": {"mode": "manual", "delay_ms": 0}}
    detailed = project_response(
        {"id": 130, "name": "音频项目", "slideshow": slideshow, "audio_settings": audio_settings},
        "project_detail",
    )
    legacy = project_response({"id": 129, "name": "旧服务项目"}, "project_detail")

    assert detailed["slideshow"] == slideshow
    assert detailed["audio_settings"]["cue_bindings"][0]["asset_name"] == "transition-forward"
    assert "slideshow" not in legacy
    assert "audio_settings" not in legacy
