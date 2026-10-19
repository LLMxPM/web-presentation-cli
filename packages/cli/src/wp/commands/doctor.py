"""文件功能：执行 CLI 诊断（连通性、PAT 有效性、默认空间与权限检测）。"""

from __future__ import annotations

import json

import click
import httpx

import wp
from wp.client import ApiClient, ApiClientError
from wp.config import get_profile, load_config
from wp.openapi_contracts import validate_registered_contracts
from wp_api_client.openapi import safe_url
from wp.formatter import print_json, print_table
from wp.skills.diagnostics import print_skill_details, skill_diagnostic


@click.command("doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """全面诊断本地 CLI 环境、服务连通性与 PAT 授权状态。"""

    cfg = load_config()
    profile = get_profile(cfg, ctx.obj.get("profile"))
    diagnostics: list[dict] = []

    # 1. CLI 版本
    diagnostics.append({"check": "CLI 版本", "value": f"v{wp.__version__}", "status": "ok"})

    # 2. 内置 Skill 与当前全局/项目安装版本
    try:
        diagnostics.append(skill_diagnostic())
    except (OSError, RuntimeError, ValueError) as exc:
        diagnostics.append({"check": "Agent Skill", "value": str(exc), "status": "error"})

    # 3. 服务端探活
    endpoint = profile.endpoint.rstrip("/")
    health_value = "不可达"
    health_status = "error"
    try:
        r = httpx.get(f"{endpoint}/api/v1/system/health", timeout=5.0)
        if r.status_code == 200:
            health = r.json()
            health_data = health if isinstance(health, dict) else {}
            backend_status = str(health_data.get("status", "unknown"))
            health_value = (
                f"{backend_status}（database={health_data.get('database')}, "
                f"redis={health_data.get('redis')}）"
            )
            health_status = "ok" if backend_status == "ok" else "warning"
        else:
            health_value = f"HTTP {r.status_code}"
    except (httpx.RequestError, ValueError) as exc:
        health_value = str(exc) or health_value
    diagnostics.append({"check": "Backend 地址", "value": f"{endpoint}：{health_value}", "status": health_status})

    # 契约检查与健康、认证独立；一次获取校验全部注册操作。
    client = ApiClient(profile)
    try:
        document = client.get_openapi_schema()
        validate_registered_contracts(ctx.find_root().command, document)
        diagnostics.append({"check": "OpenAPI", "value": "全部 CLI 请求契约有效", "status": "ok"})
    except ApiClientError as err:
        diagnostics.append({"check": "OpenAPI", "value": err.message, "status": "error", "code": err.code,
                            "details": {"url": safe_url(endpoint + "/openapi.json"), **getattr(client, "openapi_details", {}), **(err.details or {})}})
    finally:
        client.close()

    # 4. PAT 凭证检测
    token_status = "未配置"
    if profile.token:
        token_status = "已配置"
    diagnostics.append(
        {
            "check": "访问令牌 (PAT)",
            "value": token_status,
            "status": "ok" if profile.token else "warning",
        }
    )

    # 5. API 连通与权限校验
    if profile.token:
        client = ApiClient(profile)
        try:
            try:
                workspaces = client.get("/workspaces")
                diagnostics.append({"check": "授权工作空间", "value": f"{len(workspaces)} 个可用空间", "status": "ok"})
            except ApiClientError as err:
                diagnostics.append({"check": "API 认证", "value": f"认证失败: {err.message}", "status": "error"})

            ws_id = profile.default_workspace_id
            if ws_id:
                try:
                    ws = client.get(f"/workspaces/{ws_id}")
                    diagnostics.append({"check": "默认工作空间", "value": f"{ws.get('name')} (ID: {ws_id})", "status": "ok"})
                except ApiClientError:
                    diagnostics.append({"check": "默认工作空间", "value": f"访问受限 (ID: {ws_id})", "status": "error"})
            else:
                diagnostics.append({"check": "默认工作空间", "value": "未设置，请使用 wp workspace use <id>", "status": "warning"})

        finally:
            client.close()

    if ctx.obj.get("as_json"):
        print_json(diagnostics)
        ctx.exit(1 if any(item["status"] == "error" for item in diagnostics) else 0)

    status_labels = {"ok": "正常", "warning": "警告", "error": "失败"}
    rows = [[item["check"], item["value"] + ("\n" + json.dumps({"code": item["code"], "details": item["details"]}, ensure_ascii=False) if "code" in item else ""), status_labels.get(item["status"], item["status"])] for item in diagnostics]
    print_table("CLI 诊断检查报告", ["检查项", "当前状态", "判定结果"], rows)
    print_skill_details(diagnostics)

    ctx.exit(1 if any(item["status"] == "error" for item in diagnostics) else 0)
