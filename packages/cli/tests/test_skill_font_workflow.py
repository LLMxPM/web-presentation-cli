"""文件功能：执行随包 Skill 的字体注册示例并核对真实响应字段，防止文档与 CLI 同步漂移。"""

import json
from pathlib import Path
import re
import shlex
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wp.cli import main


def test_skill_font_registration_example_is_executable(tmp_path: Path) -> None:
    """从真实文档提取命令和载荷，在隔离文件系统且禁止网络时执行完整命令解析。"""

    root = Path(__file__).resolve().parents[3]
    text = (root / "skills/web-presentation/references/cli-usage.md").read_text(encoding="utf-8")
    command = next(line for line in text.splitlines() if line.startswith("wp --json font register "))
    examples = [json.loads(block) for block in re.findall(r"```json\s*(.*?)\s*```", text, re.S)]
    payload = next(item for item in examples if isinstance(item, dict) and {"asset_id", "family_name", "font_weight"} <= item.keys())
    fake = MagicMock()
    fake.register_font.return_value = {"id": 7, "family_id": 2, "asset_id": payload["asset_id"], "font_family": payload["family_name"]}
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        target = Path(".tmp/web-presentation/font-register.json")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(payload), encoding="utf-8")
        with patch("wp.commands.font.get_client", return_value=fake), patch("httpx.Client.request", side_effect=AssertionError("示例测试禁止网络请求")):
            result = runner.invoke(main, shlex.split(command)[1:])
    assert result.exit_code == 0, result.output
    fake.register_font.assert_called_once_with(payload)
    assert json.loads(result.output)["font_family"] == payload["family_name"]


def test_font_raw_preserves_backend_response_and_json_projects_real_fields() -> None:
    """以真实字段形状验证表格、JSON 与 raw，不用另一份伪造字段蒙混通过。"""

    payload = {"id": 3, "family_id": 4, "asset_id": 5, "font_family": "Brand Sans", "asset_url": "https://example.invalid/private-font"}
    fake = MagicMock()
    fake.get_font.return_value = payload
    with patch("wp.commands.font.get_client", return_value=fake), patch("httpx.Client.request", side_effect=AssertionError("输出测试禁止网络请求")):
        table = CliRunner().invoke(main, ["font", "get", "3"])
        projected = CliRunner().invoke(main, ["--json", "font", "get", "3"])
        raw = CliRunner().invoke(main, ["--raw", "font", "get", "3"])
    assert table.exit_code == projected.exit_code == raw.exit_code == 0
    assert "Brand Sans" in table.output
    assert json.loads(projected.output)["font_family"] == "Brand Sans"
    assert "asset_url" not in json.loads(projected.output)
    assert json.loads(raw.output) == payload
