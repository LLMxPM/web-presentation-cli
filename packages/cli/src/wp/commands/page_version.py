"""文件功能：提供页面历史版本的列表、详情、完整源码导出、版本比较与重点快照命令。"""

from __future__ import annotations

import difflib
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from wp.client import ApiClientError
from wp.commands.common import idempotency_key_option, get_client, handle_api_error, output_result
from wp.formatter import print_success, print_table
from wp.openapi_help import contract, openapi_command

_SNAPSHOT_NAME_MAX_LENGTH = 128
_DIFF_FIELD_CHOICES = ("source", "speaker_notes", "all")
_FIELD_LABELS = {"source": "源码", "speaker_notes": "演讲备注"}


@click.group("version")
def page_version_group() -> None:
    """页面历史版本。"""


def _require_versions(document: Any, *, page_id: int) -> list[dict[str, Any]]:
    """校验版本列表响应为对象数组，任何非对象项都按契约异常失败。"""

    if not isinstance(document, list):
        raise click.ClickException(f"页面 {page_id} 的版本响应必须是数组。")
    for index, item in enumerate(document):
        if not isinstance(item, dict):
            raise click.ClickException(f"页面 {page_id} 的版本响应第 {index} 项不是 JSON 对象。")
    return document


def _require_version_detail(document: Any, *, page_id: int, version_no: int) -> dict[str, Any]:
    """校验版本详情响应，缺失完整还原内容时立即失败。"""

    if not isinstance(document, dict):
        raise click.ClickException(f"页面 {page_id} 版本 {version_no} 的响应必须是 JSON 对象。")
    if not isinstance(document.get("resolved_content"), str):
        raise click.ClickException(
            f"页面 {page_id} 版本 {version_no} 缺少 resolved_content，无法读取完整源码。"
        )
    return document


@openapi_command(
    page_version_group,
    "list",
    contract("GET", "/api/v1/pages/{page_id}/versions"),
    examples=(
        "wp --json page version list 21 --important",
        "wp page version list 21 --limit 5",
    ),
)
@click.argument("page_id", type=click.IntRange(min=1))
@click.option("--important", "only_important", is_flag=True, help="只列出已标记的重点快照")
@click.option("--limit", type=click.IntRange(min=1), help="筛选后返回的版本数量上限")
@click.pass_context
def list_page_versions_cmd(
    ctx: click.Context,
    page_id: int,
    only_important: bool,
    limit: int | None,
) -> None:
    """列出页面历史版本，最新版本在前；筛选与数量限制在本地完成。"""

    try:
        versions = _require_versions(get_client(ctx).get(f"/pages/{page_id}/versions"), page_id=page_id)
    except ApiClientError as err:
        handle_api_error("获取页面版本失败", err)

    if only_important:
        versions = [item for item in versions if item.get("is_important")]
    if limit is not None:
        versions = versions[:limit]

    if ctx.obj.get("as_json"):
        output_result(ctx, versions)
        return

    rows = [
        [
            item.get("version_no"),
            item.get("version_label", "-"),
            "是" if item.get("is_current") else "-",
            item.get("snapshot_name") or "-",
            item.get("change_note") or "-",
            item.get("created_at") or "-",
            item.get("created_by") if item.get("created_by") is not None else "-",
        ]
        for item in versions
    ]
    print_table(
        f"页面 (ID: {page_id}) 版本历史",
        ["版本", "标签", "当前", "快照名", "修改说明", "创建时间", "创建者"],
        rows,
    )


@openapi_command(page_version_group, "get", contract("GET", "/api/v1/pages/{page_id}/versions/{version_no}"))
@click.argument("page_id", type=click.IntRange(min=1))
@click.argument("version_no", type=click.IntRange(min=1))
@click.pass_context
def get_page_version_cmd(ctx: click.Context, page_id: int, version_no: int) -> None:
    """获取页面指定版本的完整还原内容与演讲备注。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/pages/{page_id}/versions/{version_no}"))
    except ApiClientError as err:
        handle_api_error("获取页面版本内容失败", err)


@openapi_command(
    page_version_group,
    "export",
    contract("GET", "/api/v1/pages/{page_id}/versions/{version_no}"),
    examples=(
        "wp page version export 21 5 --output .tmp/web-presentation/page-21-v5.vue",
        "wp --json page version export 21 5 --output page-21-v5.vue --overwrite",
    ),
)
@click.argument("page_id", type=click.IntRange(min=1))
@click.argument("version_no", type=click.IntRange(min=1))
@click.option("--output", "-o", "output_path", required=True, type=click.Path(dir_okay=False), help="导出文件路径")
@click.option("--overwrite", is_flag=True, help="允许覆盖已存在的目标文件")
@click.pass_context
def export_page_version_cmd(
    ctx: click.Context,
    page_id: int,
    version_no: int,
    output_path: str,
    overwrite: bool,
) -> None:
    """把指定版本的完整源码以 UTF-8 原子写入文件，不把差异文本当源码。"""

    try:
        detail = _require_version_detail(
            get_client(ctx).get(f"/pages/{page_id}/versions/{version_no}"),
            page_id=page_id,
            version_no=version_no,
        )
    except ApiClientError as err:
        handle_api_error("获取页面版本内容失败", err)

    target = Path(output_path).expanduser()
    if target.exists() and not overwrite:
        raise click.ClickException(f"目标文件已存在：{target}；确认覆盖时显式追加 --overwrite。")

    payload = detail["resolved_content"].encode("utf-8")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_atomically(target, payload)
    except OSError as exc:
        raise click.ClickException(f"写入导出文件失败 '{target}': {exc}") from exc

    result = {
        "page_id": detail.get("page_id", page_id),
        "version_no": detail.get("version_no", version_no),
        "file_type": detail.get("file_type"),
        "output_path": str(target.resolve()),
        "bytes": len(payload),
    }
    if ctx.obj.get("as_json"):
        output_result(ctx, result)
        return
    print_success(f"已导出页面 {result['page_id']} 版本 {result['version_no']} 到 {result['output_path']}（{result['bytes']} 字节）")


def _write_atomically(target: Path, payload: bytes) -> None:
    """先写同目录临时文件再原子替换，避免中断留下半份源码。"""

    handle = tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False)
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _diff_field(
    *,
    from_content: str,
    to_content: str,
    from_label: str,
    to_label: str,
) -> tuple[bool, str]:
    """生成单字段 unified diff，并把完全相同的文本标记为未变化。"""

    if from_content == to_content:
        return False, ""

    diff_text = "\n".join(
        difflib.unified_diff(
            from_content.splitlines(),
            to_content.splitlines(),
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )
    if _ends_with_newline(from_content) != _ends_with_newline(to_content):
        # 仅在末尾换行不同时，逐行比较不会产生差异行，这里显式说明避免误判为无变更。
        note = "末尾换行：from 版本{}，to 版本{}".format(
            "有" if _ends_with_newline(from_content) else "无",
            "有" if _ends_with_newline(to_content) else "无",
        )
        diff_text = f"{diff_text}\n{note}" if diff_text else note
    return True, diff_text


def _ends_with_newline(text: str) -> bool:
    """判断文本是否以换行结束；空文本按没有末尾换行处理。"""

    return text.endswith(("\n", "\r"))


@openapi_command(
    page_version_group,
    "diff",
    contract("GET", "/api/v1/pages/{page_id}/versions/{version_no}"),
    examples=(
        "wp page version diff 21 5 12 --field all",
        "wp --json page version diff 21 5 12 --field speaker_notes",
    ),
)
@click.argument("page_id", type=click.IntRange(min=1))
@click.argument("from_version", type=click.IntRange(min=1))
@click.argument("to_version", type=click.IntRange(min=1))
@click.option(
    "--field",
    "field",
    type=click.Choice(_DIFF_FIELD_CHOICES),
    default="all",
    show_default=True,
    help="比较字段：源码、演讲备注或两者",
)
@click.pass_context
def diff_page_versions_cmd(
    ctx: click.Context,
    page_id: int,
    from_version: int,
    to_version: int,
    field: str,
) -> None:
    """比较同一页面两个版本的源码与演讲备注，方向为 from → to。"""

    client = get_client(ctx)
    try:
        from_detail = _require_version_detail(
            client.get(f"/pages/{page_id}/versions/{from_version}"),
            page_id=page_id,
            version_no=from_version,
        )
        if from_version == to_version:
            to_detail = from_detail
        else:
            to_detail = _require_version_detail(
                client.get(f"/pages/{page_id}/versions/{to_version}"),
                page_id=page_id,
                version_no=to_version,
            )
    except ApiClientError as err:
        handle_api_error("获取页面版本内容失败", err)

    fields = ("source", "speaker_notes") if field == "all" else (field,)
    from_label = f"v{from_version} {from_detail.get('version_label', '')}".strip()
    to_label = f"v{to_version} {to_detail.get('version_label', '')}".strip()

    comparisons: dict[str, Any] = {}
    for name in fields:
        key = "resolved_content" if name == "source" else "speaker_notes"
        from_value = from_detail.get(key)
        to_value = to_detail.get(key)
        changed, diff_text = _diff_field(
            from_content=from_value if isinstance(from_value, str) else "",
            to_content=to_value if isinstance(to_value, str) else "",
            from_label=from_label,
            to_label=to_label,
        )
        if name == "speaker_notes" and bool(from_value is None) != bool(to_value is None):
            # 备注的 null 与空串在服务端语义不同，diff 文本相同也必须报变更。
            changed = True
        comparisons[name] = {"changed": changed, "diff": diff_text}

    changed_fields = [name for name, item in comparisons.items() if item["changed"]]
    if ctx.obj.get("as_json"):
        output_result(
            ctx,
            {
                "page_id": page_id,
                "from_version_no": from_version,
                "to_version_no": to_version,
                "fields": list(fields),
                "changed": bool(changed_fields),
                "changed_fields": changed_fields,
                "comparisons": comparisons,
            },
        )
        return

    if not changed_fields:
        click.echo(f"页面 {page_id} 版本 {from_version} 与 {to_version} 在所选字段上没有差异。")
        return
    for name in fields:
        item = comparisons[name]
        click.echo(f"### {_FIELD_LABELS[name]}（{'有变更' if item['changed'] else '无变更'}）")
        if item["diff"]:
            click.echo(item["diff"])
        elif item["changed"]:
            click.echo("（文本相同，但空值与空串语义不同）")
        else:
            click.echo("（无差异）")
        click.echo("")


@openapi_command(
    page_version_group,
    "snapshot",
    contract("POST", "/api/v1/pages/{page_id}/versions/{version_no}/snapshot"),
    examples=(
        "wp page version snapshot 21 12 --name \"内容确认版\" --idempotency-key page-21-v12-checkpoint",
    ),
)
@click.argument("page_id", type=click.IntRange(min=1))
@click.argument("version_no", type=click.IntRange(min=1))
@click.option("--name", required=True, help="重点快照名称；非空且不超过 128 字符")
@idempotency_key_option
@click.pass_context
def snapshot_page_version_cmd(
    ctx: click.Context,
    page_id: int,
    version_no: int,
    name: str,
) -> None:
    """把已存在版本标记为重点快照；重复提交同一版本只重命名，不新增版本。"""

    normalized = (name or "").strip()
    if not normalized:
        raise click.BadParameter("重点快照名称不能为空。", param_hint="--name")
    if len(normalized) > _SNAPSHOT_NAME_MAX_LENGTH:
        raise click.BadParameter(
            f"重点快照名称不能超过 {_SNAPSHOT_NAME_MAX_LENGTH} 个字符。",
            param_hint="--name",
        )

    try:
        result = get_client(ctx).create_page_version_snapshot(
            page_id,
            version_no,
            snapshot_name=normalized,
        )
    except ApiClientError as err:
        handle_api_error("标记页面版本快照失败", err)

    if ctx.obj.get("as_json"):
        output_result(ctx, result)
        return
    snapshot_name = result.get("snapshot_name") if isinstance(result, dict) else None
    label = result.get("version_label") if isinstance(result, dict) else None
    print_success(f"页面 {page_id} 版本 {version_no} 已标记为重点快照 {label or ''}（{snapshot_name or normalized}）")


def register_page_version_commands(page_group: click.Group) -> None:
    """把版本子命令挂到页面命令组，保持页面命令文件只负责页面级职责。"""

    page_group.add_command(page_version_group)


__all__ = ["page_version_group", "register_page_version_commands"]
