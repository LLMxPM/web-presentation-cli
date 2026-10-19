"""文件功能：覆盖真实 CLI 校验恢复命令及候选输入保留。"""

import click
import pytest

from wp.commands.validation_recovery import with_validation_recovery


@pytest.mark.parametrize("resource", ["page", "component"])
@pytest.mark.parametrize("failed", [False, True])
def test_mutation_candidate_guidance(resource, failed):
    """成功警告与失败均应保留 edits 文件，不能回退 current。"""
    ctx = click.Context(click.Command("edit"))
    ctx.params = {f"{resource}_id": 21, "edits_file": "candidate.json"}
    job = {"job_id": "j", "job_type": f"{resource}_edit"}
    job.update({"error": {"details": {"validation": "失败"}}} if failed else {"result": {"validation": "警告"}})
    result = with_validation_recovery(ctx, job)
    assert result["validation_recovery"]["command"] == f"wp {resource} validate 21 --mode edits --edits-file candidate.json --detail"
    assert "validation_recovery" not in job


def test_create_failure_does_not_invent_id():
    """未保存候选没有 ID，只能修正原创建请求。"""
    ctx = click.Context(click.Command("create"))
    job = {"job_id": "j", "job_type": "page_create", "error": {"details": {"validation": "失败"}}}
    recovery = with_validation_recovery(ctx, job)["validation_recovery"]
    assert "command" not in recovery
    assert "尚无目标 ID" in recovery["instruction"]
