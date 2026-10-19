"""文件功能：把通用 Mutation 校验提示适配为保留候选输入的真实 CLI 恢复命令。"""

from copy import deepcopy
import shlex

import click


def with_validation_recovery(ctx: click.Context, value):
    """仅为校验结果追加客户端提示；原业务数据及源码输入保持不变。"""
    if not isinstance(value, dict) or "job_id" not in value:
        return value
    result, error = value.get("result") or {}, value.get("error") or {}
    details = error.get("details") or {} if isinstance(error, dict) else {}
    if not (result.get("validation") or details.get("validation")):
        return value
    resource = str(value.get("job_type") or "").split("_")[0]
    if resource not in {"page", "component"} and ctx.parent:
        resource = ctx.parent.info_name
    if resource not in {"page", "component"}:
        return value
    params = ctx.params
    target = params.get(f"{resource}_id") or result.get(f"{resource}_id") or value.get("target_id")
    recovery = {"instruction": "保留原候选输入，按相同目标和候选模式查看明细；不要改为校验已保存源码。"}
    if not target:
        recovery["instruction"] = "创建失败且尚无目标 ID；修正原创建候选后重新提交。"
    elif params.get("edits_file"):
        recovery["command"] = f"wp {resource} validate {target} --mode edits --edits-file {shlex.quote(str(params['edits_file']))} --detail"
    elif params.get("file_path"):
        recovery["command"] = f"wp {resource} validate {target} --mode content --source-file {shlex.quote(str(params['file_path']))} --detail"
    else:
        recovery["instruction"] += f" 使用 wp {resource} validate {target} --detail，并从原 payload 保留 content/edits 及候选契约字段。"
    return {**deepcopy(value), "validation_recovery": recovery}
