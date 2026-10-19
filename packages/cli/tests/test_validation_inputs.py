"""文件功能：验证页面与组件校验不会忽略候选文件，错误参数在创建客户端前失败。"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest

from wp.cli import main


@pytest.mark.parametrize("entity", ["page", "component"])
@pytest.mark.parametrize("mode,kind", [(None, None), ("current", None), (None, "source"),
                                      ("content", "source"), (None, "edits"), ("edits", "edits")])
def test_validation_infers_mode_and_forwards_candidate(tmp_path, entity, mode, kind):
    """自动和显式候选模式都应发送文件真实内容，无文件时保留 current。"""

    source = tmp_path / "candidate.vue"
    source.write_text("<template><p>新候选</p></template>", encoding="utf-8")
    edits = [{"type": "replace_exact", "old_text": "旧", "new_text": "新"}]
    edits_file = tmp_path / "edits.json"
    edits_file.write_text(json.dumps(edits), encoding="utf-8")
    args = ["--json", entity, "validate", "7"]
    if mode:
        args += ["--mode", mode]
    if kind:
        args += ["--source-file", str(source)] if kind == "source" else ["--edits-file", str(edits_file)]
    client = MagicMock()
    client.validate_entity.side_effect = lambda payload: {**payload, "valid": True}
    with patch(f"wp.commands.{entity}.get_client", return_value=client):
        result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    sent = client.validate_entity.call_args.args[0]
    expected_mode = "content" if kind == "source" else "edits" if kind else "current"
    assert sent["mode"] == json.loads(result.output)["mode"] == expected_mode
    if kind == "source":
        assert sent["source_code"] == source.read_text(encoding="utf-8")
    elif kind == "edits":
        assert sent["edits"] == edits
    else:
        assert "source_code" not in sent and "edits" not in sent


@pytest.mark.parametrize("entity", ["page", "component"])
@pytest.mark.parametrize("mode,files", [("current", ["source"]), ("current", ["edits"]),
    ("content", []), ("edits", []), ("content", ["edits"]), ("edits", ["source"]),
    (None, ["source", "edits"]), (None, ["empty_edits"])])
def test_validation_rejects_incompatible_inputs_before_request(tmp_path, entity, mode, files):
    """有歧义、缺失或空编辑输入不能发起当前页面校验冒充候选校验。"""

    args = ["--json", entity, "validate", "7"]
    if mode:
        args += ["--mode", mode]
    for kind in files:
        path = tmp_path / kind
        path.write_text("<template />" if kind == "source" else "[]", encoding="utf-8")
        args += ["--source-file" if kind == "source" else "--edits-file", str(path)]
    with patch(f"wp.commands.{entity}.get_client") as get_client:
        result = CliRunner().invoke(main, args)
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    get_client.assert_not_called()
