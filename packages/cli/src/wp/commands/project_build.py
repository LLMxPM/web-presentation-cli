"""文件功能：下载已知项目构建任务产物的命令，不负责发起或查询构建任务。"""

from __future__ import annotations

from pathlib import Path

import click

from wp.client import ApiClientError
from wp.commands.common import get_client, handle_api_error, output_result
from wp.formatter import print_success, print_table
from wp.openapi_help import contract, openapi_command


@click.group("build")
def project_build_group() -> None:
    """项目构建产物；当前只支持下载已知任务，不发起构建。"""


@openapi_command(
    project_build_group,
    "artifact",
    contract("GET", "/api/v1/projects/{project_id}/build-jobs/{job_id}/artifact"),
    examples=(
        "wp project build artifact 7 42 --output .tmp/web-presentation/project-7-build-42.zip",
    ),
)
@click.argument("project_id", type=int)
@click.argument("job_id", type=int)
@click.option("--output", "-o", help="ZIP 保存路径或已存在的目录；默认 project-<project_id>-build-<job_id>.zip")
@click.pass_context
def download_project_build_artifact_cmd(
    ctx: click.Context,
    project_id: int,
    job_id: int,
    output: str | None,
) -> None:
    """流式下载指定构建任务的 ZIP 产物并原子落盘。"""

    default_name = f"project-{project_id}-build-{job_id}.zip"
    save_path = Path(output) if output else Path(default_name)
    if save_path.is_dir():
        save_path = save_path / default_name
    try:
        _headers, size_bytes, local_sha256 = get_client(ctx).download_project_build_artifact(
            project_id=project_id,
            job_id=job_id,
            destination=save_path,
        )
        payload = {
            "project_id": project_id,
            "build_job_id": job_id,
            "saved_file": str(save_path.resolve()),
            "size_bytes": size_bytes,
            # 本地 hash 只用于校验落盘内容，不代表服务端可信摘要。
            "local_sha256": local_sha256,
        }
        if ctx.obj.get("as_json"):
            output_result(ctx, payload)
            return
        print_success(f"已下载构建产物 (项目 {project_id} / 任务 {job_id}) 至 [bold]{save_path}[/bold]")
        print_table(
            "构建产物下载信息",
            ["属性", "值"],
            [
                ["项目 ID", str(project_id)],
                ["构建任务 ID", str(job_id)],
                ["文件大小", f"{size_bytes} 字节"],
                ["本地 SHA-256", local_sha256],
                ["保存路径", str(save_path.resolve())],
            ],
        )
    except ApiClientError as err:
        handle_api_error("下载构建产物失败", err)


__all__ = ["project_build_group"]
