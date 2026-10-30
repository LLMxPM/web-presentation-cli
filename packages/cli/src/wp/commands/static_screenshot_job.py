"""文件功能：轮询独立静态截图任务，并保持内容不可用、任务跳过和执行失败的不同语义。"""
from __future__ import annotations
import time
from typing import Any
from wp.client import ApiClient, ApiClientError


def capture_static_job(client: ApiClient, *, page_id: int, job_id: int | None, target_version: int | None,
                       timeout: float, no_wait: bool) -> tuple[dict[str, Any], bytes | None]:
    """等待到截止时间；pending 可凭 job_id 继续查询，只从固定同源任务端点下载 ready 内容。"""
    if job_id is None:
        payload = {"target_page_version_no": target_version} if target_version is not None else {}
        job = client.post(f"/pages/{page_id}/screenshot-jobs", json_data=payload)
    else:
        job = client.get(f"/pages/{page_id}/screenshot-jobs/{job_id}")
    deadline = time.monotonic() + timeout
    expected_job_id = job_id
    while True:
        if not isinstance(job, dict) or isinstance(job.get("job_id"), bool) or not isinstance(job.get("job_id"), int) or job["job_id"] < 1 or job.get("page_id") != page_id or (expected_job_id is not None and job["job_id"] != expected_job_id):
            raise ApiClientError("截图任务响应的身份无效。", code="PAGE_SCREENSHOT_JOB_INVALID")
        job_id = job["job_id"]
        expected_job_id = job_id
        status, error = job.get("status"), job.get("error") or {}
        error = error if isinstance(error, dict) else {}
        base = {"page_id": page_id, "job_id": job_id}
        if status == "succeeded":
            result = job.get("result") or {}
            if not isinstance(result, dict) or not isinstance(result.get("screenshot_id"), str) or not result.get("screenshot_id") or isinstance(result.get("version_no"), bool) or not isinstance(result.get("version_no"), int) or result["version_no"] < 1:
                raise ApiClientError("截图成功任务缺少有效内容身份或页面版本。", code="PAGE_SCREENSHOT_JOB_INVALID")
            headers, content = client.get_bytes(f"/pages/{page_id}/screenshot-jobs/{job_id}/content")
            if str(headers.get("content-type") or "").split(";", 1)[0].lower() != "image/png":
                raise ApiClientError("截图任务内容不是 PNG。", code="INVALID_CONTENT_TYPE")
            return {**base, "status": "ready", "screenshot_id": result["screenshot_id"], "version_no": result["version_no"]}, content
        if status in {"failed", "skipped", "cancelled"}:
            # skipped 仍是任务状态，即使带静态原因码也不能伪装成内容状态。
            presentation = "skipped" if status == "skipped" else "unavailable" if error.get("code") == "STATIC_PRESENTATION_UNAVAILABLE" else "failed"
            return {**base, "status": presentation, "job_status": status, "code": error.get("code") or f"PAGE_SCREENSHOT_JOB_{str(status).upper()}", "message": error.get("message") or str(status)}, None
        if status not in {"pending", "running"}:
            raise ApiClientError("截图任务状态未知。", code="PAGE_SCREENSHOT_JOB_INVALID")
        if no_wait or time.monotonic() >= deadline:
            return {**base, "status": "pending", "job_status": status, "code": "PAGE_SCREENSHOT_PENDING"}, None
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        job = client.get(f"/pages/{page_id}/screenshot-jobs/{job_id}")
