"""文件功能：提供 CLI 命令共享的客户端、文件载荷、异步任务和输出辅助函数。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn

import click

from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.formatter import print_error, print_json
from wp.output_profiles import project_response
from wp.commands.validation_recovery import with_validation_recovery


def get_client(ctx: click.Context) -> ApiClient:
    """根据当前命令上下文创建绑定 Profile 和 Workspace 的 API Client。"""

    profile = get_profile(load_config(), ctx.obj.get("profile"))
    return ApiClient(
        profile,
        workspace_id=ctx.obj.get("workspace_id"),
        idempotency_key=ctx.obj.get("idempotency_key"),
    )


def _validate_idempotency_key(
    ctx: click.Context,
    _: click.Parameter,
    value: str | None,
) -> str | None:
    """校验并保存命令级幂等键，供当前命令创建的 API Client 使用。"""

    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise click.BadParameter("幂等键不能为空。")
    if len(normalized) > 128 or not normalized.isascii():
        raise click.BadParameter("幂等键必须是不超过 128 个字符的 ASCII 字符串。")
    ctx.ensure_object(dict)
    ctx.obj["idempotency_key"] = normalized
    return normalized


def idempotency_key_option(command: Any) -> Any:
    """为写命令增加可复用的 `--idempotency-key` 选项。"""

    return click.option(
        "--idempotency-key",
        callback=_validate_idempotency_key,
        expose_value=False,
        metavar="KEY",
        help="写操作幂等键；请求超时后可用同一键安全重放。",
    )(command)


def read_json_file(file_path: str, *, label: str = "JSON 文件") -> Any:
    """读取 UTF-8 JSON 文件，并把文件错误转换为 Click 参数错误。"""

    try:
        content = Path(file_path).read_text(encoding="utf-8")
        return json.loads(content)
    except (OSError, UnicodeDecodeError) as exc:
        raise click.ClickException(f"无法读取{label} '{file_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{label} '{file_path}' 不是合法 JSON: {exc}") from exc


def read_text_file(file_path: str, *, label: str = "文本文件") -> str:
    """读取 UTF-8 文本文件，保留原始内容。"""

    try:
        return Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise click.ClickException(f"无法读取{label} '{file_path}': {exc}") from exc


def require_object(value: Any, *, label: str) -> dict[str, Any]:
    """校验载荷根节点必须为 JSON 对象。"""

    if not isinstance(value, dict):
        raise click.ClickException(f"{label}必须是 JSON 对象。")
    return value


def require_array(value: Any, *, label: str) -> list[Any]:
    """校验载荷根节点必须为 JSON 数组。"""

    if not isinstance(value, list):
        raise click.ClickException(f"{label}必须是 JSON 数组。")
    return value


def require_ids(value: Any, *, label: str = "ID 列表") -> list[int]:
    """校验批量归档文件是只包含正整数 ID 的 JSON 数组。"""

    items = require_array(value, label=label)
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in items):
        raise click.ClickException(f"{label}必须是只包含正整数的 JSON 数组。")
    return items


def output_result(ctx: click.Context, value: Any, *, profile: str | None = None, detail: bool = False) -> None:
    """输出原始或稳定投影后的 JSON，保证 CLI 与 Agent 消费一致。"""

    if profile and not ctx.obj.get("raw"):
        value = project_response(value, profile, detail=detail)
    print_json(with_validation_recovery(ctx, value))


def handle_api_error(message: str, error: ApiClientError) -> NoReturn:
    """统一打印结构化 API 错误并以非零状态退出。"""

    print_error(
        f"{message}: {error.message}",
        code=error.code,
        details=error.details,
        request_id=error.request_id,
        retry_after=error.retry_after,
    )
    raise SystemExit(1)


def resolve_wait_job(
    client: ApiClient,
    job: dict[str, Any],
    *,
    wait: bool,
    timeout: float,
) -> dict[str, Any]:
    """按命令的 wait 选择返回入队结果或任务终态。"""

    if not wait:
        return job
    job_id = str(job.get("job_id") or "")
    if not job_id:
        raise click.ClickException("服务端未返回 job_id，无法等待异步任务。")
    return client.poll_mutation_job(job_id, timeout_seconds=timeout)


def require_success_job(job: dict[str, Any], *, ctx: click.Context | None = None) -> dict[str, Any]:
    """将失败或取消的任务转换为 CLI 失败退出。"""

    if job.get("status") in {"failed", "canceled"}:
        raw_error = job.get("error") or {}
        error = raw_error if isinstance(raw_error, dict) else {"message": str(raw_error)}
        if ctx is not None:
            if ctx.obj.get("as_json"):
                print_json(with_validation_recovery(ctx, job))
            else:
                print_error(
                    f"异步任务执行失败: {error.get('message') or '未提供错误信息。'}",
                    code=error.get("code"),
                    details=error,
                )
            raise SystemExit(1)
        raise click.ClickException(str(error.get("message") or "异步任务执行失败。"))
    return job


def confirm_archive(ids: list[int], *, yes: bool, label: str) -> None:
    """对单项或批量归档执行统一确认。"""

    if yes:
        return
    if not click.confirm(f"确定要归档 {label} {', '.join(map(str, ids))} 吗？"):
        raise click.Abort()


__all__ = [
    "confirm_archive",
    "get_client",
    "handle_api_error",
    "idempotency_key_option",
    "output_result",
    "read_json_file",
    "read_text_file",
    "require_array",
    "require_ids",
    "require_object",
    "require_success_job",
    "resolve_wait_job",
]
