"""文件功能：验证 CLI 本地帮助完整性与动态 OpenAPI 请求契约渲染。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from wp.cli import main
from wp.client import ApiClientError


def _leaf_commands() -> list[tuple[list[str], click.Command]]:
    """递归收集全部叶子命令及其调用路径。"""

    leaves: list[tuple[list[str], click.Command]] = []

    def visit(command: click.Command, path: list[str]) -> None:
        if isinstance(command, click.Group):
            for name, child in command.commands.items():
                visit(child, [*path, name])
            return
        leaves.append((path, command))

    visit(main, [])
    return leaves


def test_leaf_help_fails_offline_but_local_help_remains_available() -> None:
    """契约帮助失败，本地帮助仍成功；公开选项都有说明。"""

    runner = CliRunner()
    with patch("wp.openapi_help.ApiClient.get_openapi_schema", side_effect=ApiClientError("offline")):
        for path, command in _leaf_commands():
            result = runner.invoke(main, [*path, "--help"])
            assert result.exit_code == (1 if getattr(command, "openapi_contracts", ()) else 0), (path, result.output, result.exception)
            for parameter in command.params:
                if isinstance(parameter, click.Option):
                    assert parameter.help, (path, parameter.name)


def test_openapi_help_renders_recursive_json_and_multi_route_contracts() -> None:
    """组件复杂更新应展示两个路由、触发条件和递归引用 Schema。"""

    openapi = {
        "paths": {
            "/api/v1/components/{component_id}": {
                "patch": {
                    "parameters": [{"name": "component_id", "in": "path", "required": True}],
                    "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/LightUpdate"}}}},
                }
            },
            "/api/v1/jobs/mutations/components/metadata": {
                "post": {
                    "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/HeavyUpdate"}}}},
                }
            },
        },
        "components": {
            "schemas": {
                "LightUpdate": {"type": "object", "properties": {"name": {"type": "string"}}},
                "HeavyUpdate": {"type": "object", "properties": {"preview_schema": {"$ref": "#/components/schemas/Preview"}}},
                "Preview": {"type": "object", "properties": {"props": {"type": "object"}}},
            }
        },
    }
    client = MagicMock()
    client.get_openapi_schema.return_value = openapi
    with patch("wp.openapi_help.ApiClient", return_value=client):
        result = CliRunner().invoke(main, ["component", "update", "--help"])

    assert result.exit_code == 0, result.output
    for text in ("PATCH /api/v1/components/{component_id}", "POST /api/v1/jobs/mutations/components/metadata", "仅更新 name", "Preview"):
        assert text in result.output
    client.close.assert_called_once()


def test_openapi_help_renders_multipart_and_fails_without_partial_help() -> None:
    """上传命令应展示 multipart；读取失败时不输出部分帮助。"""

    openapi = {
        "paths": {
            "/api/v1/assets": {
                "post": {
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "file": {"type": "string", "format": "binary"},
                                    },
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    client = MagicMock()
    client.get_openapi_schema.return_value = openapi
    with patch("wp.openapi_help.ApiClient", return_value=client):
        multipart = CliRunner().invoke(main, ["asset", "upload", "--help"])
    assert multipart.exit_code == 0
    assert "multipart/form-data" in multipart.output
    assert '"format": "binary"' in multipart.output

    with patch("wp.openapi_help.ApiClient.get_openapi_schema", side_effect=ApiClientError("offline")):
        offline = CliRunner().invoke(main, ["page", "create", "--help"])
    assert offline.exit_code == 1
    assert offline.stdout == ""
    assert "offline" in offline.stderr


def test_audio_help_includes_nested_cue_schema() -> None:
    """音频帮助必须展开嵌套 cue 字段与约束，不能只返回通用请求头。"""

    document = {
        "paths": {"/api/v1/projects/{project_id}/configuration": {"put": {
            "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AudioSettings"}}}},
        }}},
        "components": {"schemas": {
            "AudioSettings": {"properties": {"cue_bindings": {"type": "array", "items": {"$ref": "#/components/schemas/AudioCueBindingInput"}}}},
            "AudioCueBindingInput": {"required": ["key", "asset_id"], "properties": {
                "key": {"type": "string"}, "asset_id": {"type": "integer", "minimum": 1},
                "gain_percent": {"type": "integer", "minimum": 0, "maximum": 100},
            }},
        }},
    }
    with patch("wp.openapi_help.ApiClient.get_openapi_schema", return_value=document):
        result = CliRunner().invoke(main, ["project", "audio", "update", "--help"])
    assert result.exit_code == 0, result.output
    for field in ("AudioCueBindingInput", '"key"', '"asset_id"', '"gain_percent"', '"maximum": 100'):
        assert field in result.output
