"""文件功能：统一页面与组件校验的候选输入推断，防止文件参数被静默忽略。"""

from __future__ import annotations

from typing import Any

import click

from wp.commands.common import read_json_file, read_text_file, require_array


def build_validation_payload(
    entity_type: str,
    entity_id: int,
    *,
    mode: str | None,
    source_file: str | None,
    edits_file: str | None,
    detail: bool,
) -> dict[str, Any]:
    """按文件推断校验模式；显式模式与输入不匹配时在请求前拒绝。"""

    if source_file and edits_file:
        raise click.UsageError("--source-file 与 --edits-file 不能同时提供。")
    inferred = "content" if source_file else "edits" if edits_file else "current"
    selected = mode or inferred
    if selected != inferred:
        requirements = {
            "current": "current 模式不能提供 --source-file 或 --edits-file。",
            "content": "content 模式必须且只能提供 --source-file。",
            "edits": "edits 模式必须且只能提供 --edits-file。",
        }
        raise click.UsageError(requirements[selected])
    payload: dict[str, Any] = {
        "entity_type": entity_type, "entity_id": entity_id, "mode": selected, "detail": detail,
    }
    if source_file:
        payload["source_code"] = read_text_file(source_file, label="候选源码")
    if edits_file:
        payload["edits"] = require_array(read_json_file(edits_file, label="候选编辑操作"), label="候选编辑操作")
        if not payload["edits"]:
            raise click.UsageError("edits 模式必须提供非空编辑数组。")
    return payload
