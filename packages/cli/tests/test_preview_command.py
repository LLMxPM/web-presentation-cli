"""文件功能：测试统一项目/页面预览地址 CLI 命令及目标参数校验。"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wp.cli import main


def test_project_preview_uses_shared_client_flow() -> None:
    """项目预览应把目标和入口路由交给CLI 同步 API Client。"""

    client = MagicMock()
    client.create_preview_artifact.return_value = {
        "preview_url": "https://example.test/preview",
        "artifact_id": "artifact-7",
        "preview_kind": "project",
        "entry_descriptor": {"route": "/overview"},
        "viewport_width": 1600,
        "viewport_height": 900,
        "project_id": 7,
        "workspace_id": 1,
    }

    with patch("wp.commands.preview.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "preview", "get", "--project-id", "7", "--route", "/overview"])

    assert result.exit_code == 0, result.output
    client.create_preview_artifact.assert_called_once_with(
        target_type="project",
        target_id=7,
        route="/overview",
    )
    assert "https://example.test/preview" in result.output


def test_page_preview_uses_same_client_flow_without_route() -> None:
    """页面预览复用同一个 Client 方法，并不在 CLI 拼接页面模块路径。"""

    client = MagicMock()
    client.create_preview_artifact.return_value = {
        "preview_url": "https://example.test/page-preview",
        "artifact_id": "artifact-21",
        "preview_kind": "page",
        "entry_descriptor": {"page_id": 21},
        "viewport_width": 1600,
        "viewport_height": 900,
        "project_id": 7,
        "workspace_id": 1,
    }

    with patch("wp.commands.preview.get_client", return_value=client):
        result = CliRunner().invoke(main, ["preview", "get", "--page-id", "21"])

    assert result.exit_code == 0, result.output
    client.create_preview_artifact.assert_called_once_with(
        target_type="page",
        target_id=21,
        route=None,
    )


def test_preview_target_options_are_mutually_exclusive() -> None:
    """预览命令必须明确选择一个目标。"""

    missing = CliRunner().invoke(main, ["preview", "get"])
    both = CliRunner().invoke(main, ["preview", "get", "--project-id", "7", "--page-id", "21"])
    page_route = CliRunner().invoke(main, ["preview", "get", "--page-id", "21", "--route", "/overview"])

    assert missing.exit_code != 0
    assert both.exit_code != 0
    assert page_route.exit_code != 0


def test_preview_requires_stable_response_fields() -> None:
    """预览响应缺少稳定交付字段时应明确失败。"""

    client = MagicMock()
    client.create_preview_artifact.return_value = {"preview_url": "https://example.test/preview"}

    with patch("wp.commands.preview.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "preview", "get", "--project-id", "7"])

    assert result.exit_code != 0
    assert "artifact_id" in result.output


def test_preview_help_defaults_to_route_without_leading_slash() -> None:
    """帮助默认示例必须跨 Shell 可用，前导斜杠只作为 Git Bash 例外说明。"""

    result = CliRunner().invoke(main, ["preview", "get", "--help"])

    assert result.exit_code == 0, result.output
    assert "wp preview get --project-id 7 --route overview" in result.output
    assert "MSYS_NO_PATHCONV=1" in result.output
