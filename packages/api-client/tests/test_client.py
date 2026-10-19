"""文件功能：验证CLI 同步 API Client 的 External API v1 路径、认证和安全边界。"""

import json
from unittest.mock import Mock

import httpx
import pytest

from wp_api_client import ApiClient, ApiClientError


def test_client_uses_external_api_v1_and_workspace_headers() -> None:
    client = ApiClient(
        endpoint="http://backend.test/",
        token="pat_secret",
        workspace_id=12,
    )
    response = Mock(spec=httpx.Response)
    response.is_success = True
    response.status_code = 200
    response.content = b'{"items": []}'
    response.headers = {"content-type": "application/json"}
    response.json.return_value = {"items": []}
    client.client.get = Mock(return_value=response)

    assert client.get("/workspaces") == {"items": []}
    request = client.client.get.call_args
    assert request.args[0] == "/api/v1/workspaces"
    assert request.kwargs["headers"]["Authorization"] == "Bearer pat_secret"
    assert request.kwargs["headers"]["X-Workspace-ID"] == "12"
    client.close()


def test_client_blocks_cross_origin_download_with_pat() -> None:
    client = ApiClient("https://backend.test", token="pat_secret")

    with pytest.raises(ApiClientError, match="安全拦截"):
        client.get_bytes("https://evil.test/private.png")

    client.close()


def test_mutation_cancel_replays_key_and_accepts_202() -> None:
    """验证取消请求路径、幂等键回显、request ID 与 202 running 响应。"""

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["key"] = request.headers["Idempotency-Key"]
        return httpx.Response(
            202,
            json={"job_id": "job-1", "status": "running"},
            headers={"X-Request-ID": "req-1"},
        )

    client = ApiClient("https://backend.test", token="pat_secret", workspace_id=12)
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))
    result = client.cancel_mutation_job("job-1", idempotency_key="cancel-key-1")

    assert captured == {"path": "/api/v1/jobs/mutations/job-1/cancel", "key": "cancel-key-1"}
    assert result["status"] == "running"
    assert result == {"job_id": "job-1", "status": "running"}
    client.close()


def test_retry_after_and_request_id_are_preserved_on_conflict() -> None:
    """验证客户端保留服务端幂等并发冲突的重试提示。"""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"code": "CONCURRENT_MUTATION_IN_PROGRESS", "message": "稍后重试", "data": {"retryable": True}},
            headers={"Retry-After": "1", "X-Request-ID": "req-conflict"},
        )

    client = ApiClient("https://backend.test", token="pat_secret")
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    with pytest.raises(ApiClientError) as caught:
        client.retry_mutation_job("job-failed", idempotency_key="retry-key")
    assert caught.value.retry_after == "1"
    assert caught.value.request_id == "req-conflict"
    assert caught.value.details == {"retryable": True}
    client.close()


def test_openapi_uses_root_path_without_credentials_and_poll_reaches_terminal(monkeypatch) -> None:
    """验证 OpenAPI 不携带凭证，并验证 pending/running 轮询到终态。"""

    statuses = iter(["pending", "running", "succeeded"])
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/openapi.json":
            assert "Authorization" not in request.headers
            assert "X-Workspace-ID" not in request.headers
            return httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})
        return httpx.Response(200, json={"job_id": "job-1", "status": next(statuses)})

    monkeypatch.setattr("wp_api_client.client.time.sleep", lambda _: None)
    client = ApiClient("https://backend.test", token="pat_secret")
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    assert client.get_openapi_schema()["openapi"] == "3.1.0"
    assert client.poll_mutation_job("job-1", interval=0)["status"] == "succeeded"
    assert paths == [
        "/openapi.json",
        "/api/v1/jobs/mutations/job-1",
        "/api/v1/jobs/mutations/job-1",
        "/api/v1/jobs/mutations/job-1",
    ]
    client.close()


def test_typed_capability_helpers_use_canonical_external_paths() -> None:
    """验证新增 typed helper 不绕过 /api/v1 且保持请求体结构。"""

    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    client = ApiClient("https://backend.test", token="pat_secret", workspace_id=9)
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    assert client.get_standard("page")["ok"] is True
    assert client.list_runtime_kit()["ok"] is True
    assert client.get_runtime_kit_item("Export.v1")["ok"] is True
    assert client.list_fonts()["ok"] is True
    assert client.validate_entity({"entity_type": "page", "entity_id": 1, "mode": "current"})["ok"] is True
    assert client.copy_page(1, {"target_project_id": 2})["ok"] is True
    assert client.create_component({"workspace_id": 9, "name": "Card"})["ok"] is True
    assert client.update_component_metadata_async({"component_id": 3, "name": "Card"})["ok"] is True

    assert paths == [
        "/api/v1/standards/page",
        "/api/v1/runtime-kit",
        "/api/v1/runtime-kit/Export.v1",
        "/api/v1/fonts",
        "/api/v1/validate/entity",
        "/api/v1/pages/1/copy",
        "/api/v1/components",
        "/api/v1/jobs/mutations/components/metadata",
    ]
    client.close()


def test_create_preview_artifact_reuses_one_typed_flow_for_project_and_page() -> None:
    """项目与页面预览应复用同一个 Client 方法，只切换资源目标路径。"""

    requests: list[tuple[str, dict[str, object] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = None
        if request.content:
            payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        return httpx.Response(200, json={"preview_url": "https://example.test/preview"})

    client = ApiClient("https://backend.test", token="pat_secret", workspace_id=9)
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    client.create_preview_artifact(target_type="project", target_id=7, route="/overview")
    client.create_preview_artifact(target_type="page", target_id=21)

    assert requests == [
        ("/api/v1/projects/7/preview-artifact", {"route": "/overview"}),
        ("/api/v1/pages/21/preview-artifact", {}),
    ]
    client.close()


def test_client_reuses_default_idempotency_key_for_write_requests() -> None:
    """验证调用方提供的默认幂等键会进入所有写请求。"""

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers["Idempotency-Key"]
        return httpx.Response(200, json={"ok": True})

    client = ApiClient("https://backend.test", token="pat_secret", idempotency_key="replay-key")
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    assert client.patch("/projects/1", json_data={"name": "项目"})["ok"] is True
    assert captured["key"] == "replay-key"
    client.close()


def test_client_preserves_validation_detail_and_handles_non_object_error() -> None:
    """验证 422 detail 不丢失，并避免非对象错误体触发 AttributeError。"""

    responses = iter(
        [
            httpx.Response(
                422,
                json={"code": "VALIDATION_ERROR", "message": "参数错误", "detail": [{"loc": ["body", "name"]}]},
            ),
            httpx.Response(400, json=["bad request"]),
        ]
    )
    client = ApiClient("https://backend.test", token="pat_secret")
    client.client.close()
    client.client = httpx.Client(
        base_url=client.endpoint,
        transport=httpx.MockTransport(lambda _: next(responses)),
    )

    with pytest.raises(ApiClientError) as validation_error:
        client.get("/projects")
    assert validation_error.value.details == [{"loc": ["body", "name"]}]

    with pytest.raises(ApiClientError) as list_error:
        client.get("/projects")
    assert list_error.value.details == ["bad request"]
    client.close()


def test_client_wraps_transport_errors() -> None:
    """验证连接失败统一转换为稳定的网络错误码。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = ApiClient("https://backend.test", token="pat_secret")
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    with pytest.raises(ApiClientError) as caught:
        client.get("/workspaces")
    assert caught.value.code == "NETWORK_ERROR"
    assert caught.value.status_code == 503
    client.close()


def test_openapi_rejects_invalid_payload_without_leaking_credentials() -> None:
    """OpenAPI 响应必须含 paths，且请求不能携带 PAT。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"openapi": "3.1.0"})

    client = ApiClient("https://backend.test", token="pat_secret", workspace_id=12)
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))

    with pytest.raises(ApiClientError) as caught:
        client.get_openapi_schema()
    assert caught.value.code == "OPENAPI_INVALID"
    client.close()


def _mock_transport_client(handler) -> ApiClient:
    """构造使用 MockTransport 的客户端，便于验证流式下载与错误响应。"""

    client = ApiClient("https://backend.test", token="pat_secret", workspace_id=9)
    client.client.close()
    client.client = httpx.Client(base_url=client.endpoint, transport=httpx.MockTransport(handler))
    return client


def test_download_file_streams_to_destination_and_returns_local_hash(tmp_path) -> None:
    """流式下载应原子落盘、返回字节数与本地 SHA-256，且不留下临时文件。"""

    import hashlib

    payload = b"PK\x03\x04" + b"zip-bytes" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Workspace-ID"] == "9"
        return httpx.Response(200, headers={"content-type": "application/zip"}, content=payload)

    client = _mock_transport_client(handler)
    destination = tmp_path / "nested" / "artifact.zip"
    _headers, size, digest = client.download_file("/projects/1/build-jobs/2/artifact", destination)

    assert destination.read_bytes() == payload
    assert size == len(payload)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert list(destination.parent.glob(".*.tmp.*")) == []
    client.close()


def test_download_file_error_response_does_not_create_destination(tmp_path) -> None:
    """错误响应必须在落盘前中断，不能留下半个产物。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "BUILD_ARTIFACT_NOT_FOUND", "message": "不存在"})

    client = _mock_transport_client(handler)
    destination = tmp_path / "artifact.zip"
    with pytest.raises(ApiClientError) as exc_info:
        client.download_file("/projects/1/build-jobs/2/artifact", destination)

    assert exc_info.value.code == "BUILD_ARTIFACT_NOT_FOUND"
    assert not destination.exists()
    client.close()


def test_download_project_build_artifact_rejects_non_zip_without_overwriting(tmp_path) -> None:
    """Content-Type 非 ZIP 时拒绝落盘，并保留已有目标文件。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>gateway</html>")

    client = _mock_transport_client(handler)
    destination = tmp_path / "artifact.zip"
    destination.write_bytes(b"previous")
    with pytest.raises(ApiClientError) as exc_info:
        client.download_project_build_artifact(1, 2, destination)

    assert exc_info.value.code == "INVALID_CONTENT_TYPE"
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.glob(".*.download.*")) == []
    client.close()
