"""文件功能：验证 CLI 原样输出 Mutation 的新增截图描述并兼容无截图的旧响应。"""

import json
from unittest.mock import patch

import click
import pytest

from wp.commands.common import output_result


@pytest.mark.parametrize("screenshot", [None, {"status": "ready", "version_no": 2, "screenshot_id": "a" * 64, "width": 1920, "height": 1080}])
def test_output_keeps_screenshot_increment(screenshot):
    """没有 Mutation 投影白名单，字段存在则保留；旧结果不补造截图。"""
    ctx = click.Context(click.Command("get"), obj={})
    job = {"job_id": "j", "status": "succeeded", "result": {"page_id": 21}}
    if screenshot:
        job["result"]["screenshot"] = screenshot
    with patch("wp.commands.common.print_json") as output:
        output_result(ctx, job)
    assert output.call_args.args[0] == job
