"""文件功能：提供工作空间组件的查询、创建、编辑、校验、发布与归档命令。"""

from __future__ import annotations

import click

from wp.client import ApiClientError
from wp.commands.common import (
    confirm_archive,
    get_client,
    handle_api_error,
    idempotency_key_option,
    output_result,
    read_json_file,
    read_text_file,
    require_array,
    require_ids,
    require_object,
    require_success_job,
    resolve_wait_job,
)
from wp.config import get_profile, load_config
from wp.commands.validation_input import build_validation_payload
from wp.formatter import print_table
from wp.openapi_help import contract, openapi_command


@click.group("component")
def component_group() -> None:
    """工作空间组件管理与 Mutation 任务。"""


@openapi_command(component_group, "list", contract("GET", "/api/v1/components"))
@click.option("--page", default=1, type=int, show_default=True, help="结果页码")
@click.option("--page-size", default=50, type=int, show_default=True, help="每页返回数量")
@click.option("--keyword", help="按名称、导入标识或摘要搜索")
@click.option("--scope", type=click.Choice(["all", "suggested"]), default="all", show_default=True, help="查询全部组件或指定项目的建议组件")
@click.option("--project-id", type=int, help="scope=suggested 时必填的项目 ID")
@click.pass_context
def list_components_cmd(ctx: click.Context, page: int, page_size: int, keyword: str | None, scope: str, project_id: int | None) -> None:
    """查询工作空间组件或项目建议组件。"""

    if scope == "suggested" and project_id is None:
        raise click.UsageError("scope=suggested 时必须提供 --project-id。")
    params = {"page": page, "page_size": page_size, "keyword": keyword, "scope": scope, "project_id": project_id}
    try:
        result = get_client(ctx).get("/components", params={key: value for key, value in params.items() if value is not None})
        if ctx.obj.get("as_json"):
            output_result(ctx, result, profile="component_list")
            return
        def _resolve_import_path(item: dict) -> str:
            if item.get("import_path"):
                return str(item["import_path"])
            code = item.get("code")
            version_no = item.get("current_version_no")
            if code and isinstance(version_no, int) and version_no > 0:
                return f"@workspace-components/{code}/v/{version_no}"
            if isinstance(version_no, int) and version_no <= 0:
                return "未发布"
            return "-"

        rows = [
            [
                item.get("id"),
                item.get("import_name", "-"),
                item.get("name", "-"),
                item.get("component_type", "-"),
                item.get("status", "-"),
                _resolve_import_path(item),
            ]
            for item in result.get("items", [])
        ]
        print_table("组件列表", ["ID", "导入标识", "名称", "类型", "状态", "引用路径"], rows)
    except ApiClientError as err:
        handle_api_error("获取组件列表失败", err)


@openapi_command(component_group, "get", contract("GET", "/api/v1/components/{component_id}"))
@click.argument("component_id", type=int)
@click.pass_context
def get_component_cmd(ctx: click.Context, component_id: int) -> None:
    """获取组件详情。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/components/{component_id}"), profile="component_detail")
    except ApiClientError as err:
        handle_api_error("获取组件失败", err)


@openapi_command(
    component_group,
    "create",
    contract("POST", "/api/v1/components"),
    examples=(
        'wp component create --name "指标卡" --import-name MetricCard --file .tmp/web-presentation/component-new.vue --type content --idempotency-key component-metric-card',
    ),
)
@click.option("--name", help="组件显示名称；直接参数模式必填")
@click.option("--import-name", help="稳定导入标识；直接参数模式必填")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), help="完整 Vue 3 SFC 文件；直接参数模式必填")
@click.option("--type", "component_type", default="content", show_default=True, help="组件类型：content、page、atomic 或服务端兼容别名")
@click.option("--description", help="组件用途和复用边界说明")
@click.option("--preview-schema-file", type=click.Path(exists=True, dir_okay=False), help="覆盖请求体 preview_schema 的 JSON 对象")
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), help="完整组件创建 JSON 请求体；提供后忽略其它内容参数")
@click.option("--wait/--no-wait", default=True, help="等待任务终态；--no-wait 只返回入队结果")
@click.option("--timeout", type=float, default=120.0, show_default=True, help="等待任务终态的最长秒数")
@idempotency_key_option
@click.pass_context
def create_component_cmd(
    ctx: click.Context,
    name: str | None,
    import_name: str | None,
    file_path: str | None,
    component_type: str,
    description: str | None,
    preview_schema_file: str | None,
    payload_file: str | None,
    wait: bool,
    timeout: float,
) -> None:
    """提交组件创建 Mutation Job；直接参数模式必须提供名称、导入标识和完整 SFC。"""

    profile = get_profile(load_config(), ctx.obj.get("profile"))
    workspace_id = ctx.obj.get("workspace_id") or profile.default_workspace_id
    if not workspace_id:
        raise click.UsageError("必须通过 --workspace 或 Profile 默认配置指定工作空间。")
    if payload_file:
        payload = require_object(read_json_file(payload_file, label="组件创建载荷"), label="组件创建载荷")
    else:
        if not name or not import_name or not file_path:
            raise click.UsageError("未使用 --payload-file 时必须提供 --name、--import-name 和 --file。")
        payload = {
            "workspace_id": workspace_id,
            "import_name": import_name,
            "name": name,
            "component_type": component_type,
            "source_code": read_text_file(file_path, label="组件源码"),
            "description": description,
        }
    if preview_schema_file:
        payload["preview_schema"] = read_json_file(preview_schema_file, label="Preview Schema")
    try:
        client = get_client(ctx)
        result = resolve_wait_job(client, client.create_component(payload), wait=wait, timeout=timeout)
        if wait:
            require_success_job(result, ctx=ctx)
        output_result(ctx, result)
    except ApiClientError as err:
        handle_api_error("提交组件创建失败", err)


@openapi_command(
    component_group,
    "update",
    contract("PATCH", "/api/v1/components/{component_id}", "仅更新 name 或 summary 时"),
    contract("POST", "/api/v1/jobs/mutations/components/metadata", "包含 import_name、component_type 或 preview_schema 时"),
    examples=(
        "wp component update 15 --payload-file .tmp/web-presentation/component-15-update.json --idempotency-key component-15-metadata",
    ),
)
@click.argument("component_id", type=int)
@click.option("--payload-file", type=click.Path(exists=True, dir_okay=False), required=True, help="组件元数据 JSON 请求体；复杂字段会自动进入异步任务")
@click.option("--preview-schema-file", type=click.Path(exists=True, dir_okay=False), help="覆盖 payload 中的 Preview Schema JSON")
@click.option("--wait/--no-wait", default=True, help="复杂字段更新时等待任务终态；轻量更新忽略此选项")
@click.option("--timeout", type=float, default=120.0, show_default=True, help="等待复杂字段更新任务的最长秒数")
@idempotency_key_option
@click.pass_context
def update_component_cmd(
    ctx: click.Context,
    component_id: int,
    payload_file: str,
    preview_schema_file: str | None,
    wait: bool,
    timeout: float,
) -> None:
    """更新组件元数据，复杂字段自动进入异步校验任务。"""

    payload = require_object(read_json_file(payload_file, label="组件更新载荷"), label="组件更新载荷")
    if preview_schema_file:
        payload["preview_schema"] = require_object(
            read_json_file(preview_schema_file, label="Preview Schema"),
            label="Preview Schema",
        )
    try:
        client = get_client(ctx)
        if any(field in payload for field in ("import_name", "component_type", "preview_schema")):
            job = client.update_component_metadata_async({"component_id": component_id, **payload})
            result = resolve_wait_job(client, job, wait=wait, timeout=timeout)
            if wait:
                require_success_job(result, ctx=ctx)
            output_result(ctx, result)
            return
        output_result(ctx, client.patch(f"/components/{component_id}", json_data=payload))
    except ApiClientError as err:
        handle_api_error("更新组件失败", err)


@openapi_command(
    component_group,
    "edit",
    contract("POST", "/api/v1/components/{component_id}/edits"),
    examples=(
        "wp component edit 15 --base-version-no 2 --base-draft-hash <hash> --edits-file .tmp/web-presentation/edits-15.json --idempotency-key component-15-edit",
    ),
)
@click.argument("component_id", type=int)
@click.option("--edits-file", type=click.Path(exists=True, dir_okay=False), required=True, help="结构化编辑 JSON 数组；完整字段以当前 OpenAPI Schema 为准")
@click.option("--base-version-no", type=int, required=True, help="component get 返回的最新发布版本基线")
@click.option("--base-draft-hash", required=True, help="component get 返回的最新草稿哈希基线")
@click.option("--wait/--no-wait", default=True, help="等待任务终态；--no-wait 只返回入队结果")
@click.option("--timeout", type=float, default=120.0, show_default=True, help="等待任务终态的最长秒数")
@idempotency_key_option
@click.pass_context
def edit_component_cmd(ctx: click.Context, component_id: int, edits_file: str, base_version_no: int, base_draft_hash: str, wait: bool, timeout: float) -> None:
    """提交组件源码结构化编辑任务。"""

    edits = require_array(read_json_file(edits_file, label="组件编辑操作"), label="组件编辑操作")
    try:
        client = get_client(ctx)
        payload = {"component_id": component_id, "base_version_no": base_version_no, "base_draft_hash": base_draft_hash, "edits": edits}
        result = resolve_wait_job(client, client.edit_component(component_id, payload), wait=wait, timeout=timeout)
        if wait:
            require_success_job(result, ctx=ctx)
        output_result(ctx, result)
    except ApiClientError as err:
        handle_api_error("提交组件编辑失败", err)


@component_group.group("version")
def component_version_group() -> None:
    """组件历史发布版本。"""


@openapi_command(component_version_group, "list", contract("GET", "/api/v1/components/{component_id}/versions"))
@click.argument("component_id", type=int)
@click.pass_context
def list_component_versions_cmd(ctx: click.Context, component_id: int) -> None:
    """列出组件版本。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/components/{component_id}/versions"))
    except ApiClientError as err:
        handle_api_error("获取组件版本失败", err)


@openapi_command(component_version_group, "get", contract("GET", "/api/v1/components/{component_id}/versions/{version_no}"))
@click.argument("component_id", type=int)
@click.argument("version_no", type=int)
@click.pass_context
def get_component_version_cmd(ctx: click.Context, component_id: int, version_no: int) -> None:
    """获取组件指定版本。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/components/{component_id}/versions/{version_no}"))
    except ApiClientError as err:
        handle_api_error("获取组件版本内容失败", err)


@openapi_command(component_group, "dependencies", contract("GET", "/api/v1/components/{component_id}/dependencies"))
@click.argument("component_id", type=int)
@click.pass_context
def component_dependencies_cmd(ctx: click.Context, component_id: int) -> None:
    """获取组件当前版本依赖。"""

    try:
        output_result(ctx, get_client(ctx).get(f"/components/{component_id}/dependencies"))
    except ApiClientError as err:
        handle_api_error("获取组件依赖失败", err)


@openapi_command(
    component_group,
    "validate",
    contract("POST", "/api/v1/validate/entity"),
    examples=(
        "wp --json component validate 15 --mode content --source-file .tmp/web-presentation/component-15.vue --detail",
    ),
)
@click.argument("component_id", type=int)
@click.option("--mode", type=click.Choice(["current", "content", "edits"]), default=None, help="省略时按源码/编辑文件推断 content/edits，无文件时校验 current")
@click.option("--source-file", type=click.Path(exists=True, dir_okay=False), help="content 模式必填的完整候选 SFC")
@click.option("--edits-file", type=click.Path(exists=True, dir_okay=False), help="edits 模式必填的结构化编辑 JSON 数组")
@click.option("--preview-schema-file", type=click.Path(exists=True, dir_okay=False), help="可选的候选 preview_schema JSON 对象")
@click.option("--detail", is_flag=True, help="返回完整编译、渲染和布局诊断")
@click.pass_context
def validate_component_cmd(ctx: click.Context, component_id: int, mode: str | None, source_file: str | None, edits_file: str | None, preview_schema_file: str | None, detail: bool) -> None:
    """校验组件当前或候选源码。"""

    payload = build_validation_payload(
        "component", component_id, mode=mode, source_file=source_file, edits_file=edits_file, detail=detail,
    )
    if preview_schema_file:
        payload["preview_schema"] = require_object(read_json_file(preview_schema_file, label="Preview Schema"), label="Preview Schema")
    try:
        output_result(ctx, get_client(ctx).validate_entity(payload), profile="validation", detail=detail)
    except ApiClientError as err:
        handle_api_error("组件校验失败", err)


@openapi_command(component_group, "publish", contract("POST", "/api/v1/components/{component_id}/publish"))
@click.argument("component_id", type=int)
@click.option("--release-name", help="本次发布版本的可读名称")
@click.option("--change-note", help="本次发布的变更说明")
@idempotency_key_option
@click.pass_context
def publish_component_cmd(ctx: click.Context, component_id: int, release_name: str | None, change_note: str | None) -> None:
    """发布组件当前草稿。"""

    try:
        output_result(ctx, get_client(ctx).post(f"/components/{component_id}/publish", json_data={"release_name": release_name, "change_note": change_note}))
    except ApiClientError as err:
        handle_api_error("发布组件失败", err)


@openapi_command(
    component_group,
    "archive",
    contract("POST", "/api/v1/components/{component_id}/archive", "提供 COMPONENT_ID 时"),
    contract("POST", "/api/v1/components/batch-archive", "提供 --ids-file 时"),
)
@click.argument("component_id", type=int, required=False)
@click.option("--ids-file", type=click.Path(exists=True, dir_okay=False), help="批量归档的正整数 ID JSON 数组")
@click.option("--yes", is_flag=True, help="仅在用户已明确授权归档时跳过交互确认")
@idempotency_key_option
@click.pass_context
def archive_component_cmd(ctx: click.Context, component_id: int | None, ids_file: str | None, yes: bool) -> None:
    """归档单个组件或 JSON 数组指定的一批组件；两种目标输入只能选一种。"""

    try:
        client = get_client(ctx)
        if ids_file:
            ids = require_ids(read_json_file(ids_file, label="归档 ID"))
            confirm_archive(ids, yes=yes, label="组件")
            output_result(ctx, client.post("/components/batch-archive", json_data={"ids": ids}), profile="archive")
            return
        if component_id is None:
            raise click.UsageError("必须提供 component_id 或 --ids-file。")
        confirm_archive([component_id], yes=yes, label="组件")
        output_result(ctx, client.post(f"/components/{component_id}/archive"))
    except ApiClientError as err:
        handle_api_error("归档组件失败", err)
