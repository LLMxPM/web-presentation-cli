"""文件功能：测试 CLI 命令行工具 (wp) 的命令注册、参数解析、格式化输出与错误处理。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 确保能定位到 cli/src
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from click.testing import CliRunner
from wp.cli import main
from wp.config import CliConfig, ProfileConfig, load_config, save_config
import wp.config as config_module


def test_cli_help() -> None:
    """测试 CLI 顶层与子命令帮助信息输出。"""

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Web Presentation 官方命令行工具 (wp)" in result.output
    assert "workspace" in result.output
    assert "project" in result.output
    assert "page" in result.output
    assert "preview" in result.output
    assert "component" in result.output
    assert "asset" in result.output
    assert "build" not in result.output
    assert "guide" not in result.output
    assert "job" in result.output
    assert "validate" not in result.output
    assert "doctor" in result.output
    assert "screenshot" not in result.output
    assert "profile" in result.output


def test_cli_version() -> None:
    """测试顶层 --version 输出 CLI 包的当前版本。"""

    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "wp, version 0.3.3"


def test_raw_option_is_exposed_and_mutually_exclusive_with_json() -> None:
    """顶层帮助应暴露原始 JSON 模式，两个机器输出模式不能并用。"""

    help_result = CliRunner().invoke(main, ["--help"])
    conflict_result = CliRunner().invoke(main, ["--json", "--raw", "project", "list"])

    assert "--raw" in help_result.output
    assert conflict_result.exit_code != 0


def test_page_validate_help_describes_structured_edits() -> None:
    """页面校验帮助应说明 edits 文件的字段和允许的操作类型。"""

    result = CliRunner().invoke(main, ["page", "validate", "--help"])

    assert result.exit_code == 0, result.output
    for text in (
        "replace_exact",
        "old_text",
        "insert_after",
        "anchor_text",
        "rewrite_file",
        "content",
    ):
        assert text in result.output


def test_project_list_filters_archived_projects() -> None:
    """项目列表默认只请求 active 项目，避免归档项目混入。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {"items": [], "total": 0}

    with patch("wp.commands.project.ApiClient", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "project", "list"])

    assert result.exit_code == 0, result.output
    fake_client.get.assert_called_once_with(
        "/projects",
        params={"page": 1, "page_size": 20, "status": "active"},
    )


def test_page_list_filters_archived_pages() -> None:
    """页面列表默认只请求 active 页面，避免归档页面混入。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {"items": [], "total": 0}

    with patch("wp.commands.page.ApiClient", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "page", "list", "--project-id", "7"])

    assert result.exit_code == 0, result.output
    fake_client.get.assert_called_once_with(
        "/projects/7/pages",
        params={"page": 1, "page_size": 50, "status": "active"},
    )



def test_cli_doctor_unconfigured(monkeypatch, tmp_path) -> None:
    """测试在未配置环境时的 doctor 输出。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    health_response = MagicMock(status_code=503)
    monkeypatch.setattr("wp.commands.doctor.httpx.get", lambda *args, **kwargs: health_response)

    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 1
    assert "CLI 诊断检查报告" in result.output
    assert "CLI 版本" in result.output


def test_cli_json_mode(monkeypatch, tmp_path) -> None:
    """测试全局 --json 选项。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    health_response = MagicMock(status_code=503)
    monkeypatch.setattr("wp.commands.doctor.httpx.get", lambda *args, **kwargs: health_response)

    runner = CliRunner()
    result = runner.invoke(main, ["--json", "doctor"])
    assert result.exit_code == 1
    diagnostics = json.loads(result.output)
    assert diagnostics[0]["check"] == "CLI 版本"
    assert all("[green]" not in item["value"] for item in diagnostics)


def test_page_create_failed_job_returns_nonzero_and_json(tmp_path) -> None:
    """页面创建任务失败时应保留完整任务 JSON 并返回非零状态。"""

    payload_file = tmp_path / "page.json"
    payload_file.write_text(
        json.dumps({"project_id": 1, "name": "失败页面", "source_code": "<template />"}),
        encoding="utf-8",
    )
    fake_client = MagicMock()
    fake_client.create_page.return_value = {"job_id": "job-1", "status": "pending"}
    fake_client.poll_mutation_job.return_value = {
        "job_id": "job-1",
        "status": "failed",
        "error": {"code": "CODE_CHECK_FAILED", "message": "代码检查失败"},
    }

    with patch("wp.commands.page.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "page", "create", "--payload-file", str(payload_file)],
        )

    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "failed"


def test_page_create_succeeded_job_outputs_validation(tmp_path) -> None:
    """页面创建任务成功时应输出包含 validation 布局诊断的结果 JSON。"""

    payload_file = tmp_path / "page.json"
    payload_file.write_text(
        json.dumps({"project_id": 1, "name": "正常页面", "source_code": "<template><div /></template>"}),
        encoding="utf-8",
    )
    fake_client = MagicMock()
    fake_client.create_page.return_value = {"job_id": "job-1", "status": "pending"}
    fake_client.poll_mutation_job.return_value = {
        "job_id": "job-1",
        "status": "succeeded",
        "result": {
            "page_id": 42,
            "page_code": "page-42",
            "version_no": 1,
            "validation": "检查结论：passed_with_warnings\n摘要：页面代码检查通过，发现 1 个布局警告。\n警告：\n- [PAGE_RENDER_BOTTOM_OVERFLOW] 页面底部超出画布 42px。",
        },
        "error": None,
    }

    with patch("wp.commands.page.get_client", return_value=fake_client):
        result = CliRunner().invoke(
            main,
            ["--json", "page", "create", "--payload-file", str(payload_file)],
        )

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["status"] == "succeeded"
    assert parsed["result"]["page_id"] == 42
    assert "PAGE_RENDER_BOTTOM_OVERFLOW" in parsed["result"]["validation"]


def test_whoami_uses_identity_endpoint() -> None:
    """whoami 应调用 External API 的身份接口，而不是工作空间列表接口。"""

    fake_client = MagicMock()
    fake_client.get.return_value = {
        "user": {"id": 7, "username": "agent", "role": "member", "status": "active"},
        "token": {"token_public_id": "pat_public", "scopes": ["workspace:read"]},
        "workspaces": [{"id": 1, "name": "演示空间", "role": "owner"}],
    }

    with patch("wp.commands.auth.ApiClient", return_value=fake_client):
        result = CliRunner().invoke(main, ["--json", "whoami"])

    assert result.exit_code == 0, result.output
    fake_client.get.assert_called_once_with("/auth/whoami")
    assert json.loads(result.output)["user"]["username"] == "agent"


def test_profile_list_json_does_not_expose_token(monkeypatch, tmp_path) -> None:
    """测试 Profile 列表包含默认空间但不输出 PAT。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    save_config(
        CliConfig(
            current_profile="production",
            profiles={
                "default": ProfileConfig(token="default_secret"),
                "production": ProfileConfig(
                    endpoint="https://api.example.com",
                    token="production_secret",
                    default_workspace_id=42,
                ),
            },
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--json", "profile", "list"])

    assert result.exit_code == 0
    assert '"current_profile": "production"' in result.output
    assert '"default_workspace_id": 42' in result.output
    assert "production_secret" not in result.output


def test_profile_use_persists_current_profile(monkeypatch, tmp_path) -> None:
    """测试切换默认 Profile 会持久化当前 Profile。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    save_config(
        CliConfig(
            profiles={
                "default": ProfileConfig(),
                "production": ProfileConfig(
                    endpoint="https://api.example.com",
                    default_workspace_id=42,
                ),
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["profile", "use", "production"])

    assert result.exit_code == 0
    assert load_config().current_profile == "production"
    assert "production" in result.output


def test_profile_use_rejects_unknown_profile(monkeypatch, tmp_path) -> None:
    """测试不能把不存在的 Profile 设置为默认 Profile。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    save_config(CliConfig())

    runner = CliRunner()
    result = runner.invoke(main, ["profile", "use", "missing"])

    assert result.exit_code == 1
    assert "PROFILE_NOT_FOUND" in result.output


def test_corrupt_config_is_backed_up_before_reset(monkeypatch, tmp_path) -> None:
    """损坏配置应先备份，不能静默覆盖原始凭证和 Profile。"""

    config_path = tmp_path / "config.json"
    config_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_path)

    config = load_config()

    assert config.current_profile == "default"
    backups = list(tmp_path.glob("config.json.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not-json"
    assert not config_path.exists()


def test_archive_usage_error_is_rendered_without_traceback() -> None:
    """归档命令缺少目标时应返回 Click 错误，而不是 Python traceback。"""

    result = CliRunner().invoke(main, ["asset", "archive", "--yes"])

    assert result.exit_code != 0
    assert "必须提供 asset_id 或 --ids-file" in result.output
    assert "Traceback" not in result.output


def test_write_commands_expose_idempotency_key_option() -> None:
    """所有代表性写命令都应暴露可复用的幂等键选项。"""

    for args in (
        ["project", "update", "1", "--help"],
        ["page", "create", "--help"],
        ["component", "publish", "1", "--help"],
        ["asset", "update", "1", "--help"],
        ["theme", "update", "1", "--help"],
        ["style", "update", "1", "--help"],
    ):
        result = CliRunner().invoke(main, args)
        assert result.exit_code == 0, (args, result.output)
        assert "--idempotency-key" in result.output


def test_command_idempotency_key_is_passed_to_client(monkeypatch, tmp_path) -> None:
    """验证命令行幂等键会进入共享 Client，而不是只停留在 Click 参数层。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    fake_client = MagicMock()
    fake_client.post.return_value = {"project_id": 1}

    with patch("wp.commands.common.ApiClient", return_value=fake_client) as client_class:
        result = CliRunner().invoke(
            main,
            ["project", "create", "--name", "演示项目", "--idempotency-key", "replay-key"],
        )

    assert result.exit_code == 0, result.output
    assert client_class.call_args.kwargs["idempotency_key"] == "replay-key"
    fake_client.post.assert_called_once_with("/projects", json_data={"name": "演示项目", "description": None})


def test_component_list_displays_import_path_column(monkeypatch, tmp_path) -> None:
    """组件列表表格必须包含'引用路径'列并正确展示已发布与未发布组件的路径提示。"""

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    save_config(CliConfig(current_profile="default", profiles={"default": ProfileConfig(api_url="http://localhost:8000", pat="test-pat", default_workspace_id=1)}))

    fake_client = MagicMock()
    fake_client.get.return_value = {
        "items": [
            {
                "id": 1,
                "code": "CMP001",
                "import_name": "MetricCard",
                "name": "指标卡",
                "component_type": "content",
                "status": "active",
                "current_version_no": 2,
                "import_path": "@workspace-components/CMP001/v/2",
                "import_statement": "import MetricCard from '@workspace-components/CMP001/v/2'",
            },
            {
                "id": 2,
                "code": "CMP002",
                "import_name": "DraftCard",
                "name": "草稿卡",
                "component_type": "content",
                "status": "active",
                "current_version_no": 0,
            },
        ],
        "total": 2,
        "page": 1,
        "page_size": 50,
    }

    with patch("wp.commands.common.ApiClient", return_value=fake_client):
        table_result = CliRunner(env={"COLUMNS": "120"}).invoke(main, ["component", "list"])
        json_result = CliRunner().invoke(main, ["--json", "component", "list"])

    assert table_result.exit_code == 0, table_result.output
    assert "引用路径" in table_result.output
    assert "@workspace-components/CMP001/v/2" in table_result.output
    assert "未发布" in table_result.output

    assert json_result.exit_code == 0, json_result.output
    data = json.loads(json_result.output)
    assert data["items"][0]["import_path"] == "@workspace-components/CMP001/v/2"
    assert data["items"][0]["import_statement"] == "import MetricCard from '@workspace-components/CMP001/v/2'"
    assert data["items"][1].get("import_path") is None
