"""文件功能：验证资源覆盖上传的显式选择、默认不覆盖及冲突恢复指引。"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest

from wp.cli import main
from wp.client import ApiClientError


@pytest.mark.parametrize("overwrite", [False, True])
def test_upload_only_overwrites_when_explicit(tmp_path, overwrite):
    """默认上传不携带覆盖许可，显式选择时才进入 multipart 表单。"""

    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"test-audio")
    client = MagicMock()
    client.upload.return_value = {"id": 9}
    args = ["--json", "asset", "upload", str(audio), "--type", "audio", "--idempotency-key", "upload-9"]
    if overwrite:
        args.append("--overwrite")
    with patch("wp.commands.asset.get_client", return_value=client):
        result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    data = client.upload.call_args.kwargs["data"]
    assert data.get("overwrite") == ("true" if overwrite else None)
    assert client.upload.call_args.kwargs["files"]["file"][2] == "audio/mpeg"


def test_upload_conflict_explains_both_recovery_paths(tmp_path):
    """服务端重名错误保留错误码，同时给出覆盖和按版本替换入口。"""

    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"test-audio")
    client = MagicMock()
    client.upload.side_effect = ApiClientError("请确认是否覆盖", code="ASSET_NAME_CONFLICT")
    with patch("wp.commands.asset.get_client", return_value=client):
        result = CliRunner().invoke(main, ["asset", "upload", str(audio), "--type", "audio"])
    assert result.exit_code == 1
    for hint in ("ASSET_NAME_CONFLICT", "--overwrite", "wp asset replace"):
        assert hint in result.output


def test_model3d_overwrite_fails_before_request(tmp_path):
    """三维模型仍必须按 ID 和版本基线替换，不能走通用覆盖。"""

    model = tmp_path / "model.glb"
    model.write_bytes(b"test-model")
    with patch("wp.commands.asset.get_client") as get_client:
        result = CliRunner().invoke(main, ["asset", "upload", str(model), "--type", "model3d", "--overwrite"])
    assert result.exit_code != 0
    assert "--expected-file-hash" in result.output
    get_client.assert_not_called()
