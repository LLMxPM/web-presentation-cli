"""文件功能：验证路由追加保留当前树、分组和原始覆盖，并拒绝意外重绑定。"""

from copy import deepcopy
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest

from wp.cli import main
from test_project_slideshow import ROUTE_TREE


@pytest.mark.parametrize("parent", [None, "chapter"])
def test_route_add_preserves_current_nodes_and_overrides(parent):
    """顶层和子节点新增都只追加到指定同级，保留所有既有节点及覆盖。"""

    baseline = deepcopy(ROUTE_TREE)
    client = MagicMock()
    client.get.return_value = baseline
    client.put.return_value = {"routes": []}
    args = ["--json", "project", "route", "add", "7", "--page-id", "13", "--route", "details"]
    if parent:
        args += ["--parent", parent]
    with patch("wp.commands.project_route_add.get_client", return_value=client):
        result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    payload = client.put.call_args.kwargs["json_data"]
    siblings = payload["routes"][1]["children"] if parent else payload["routes"]
    assert siblings[-1]["page_id"] == 13
    assert siblings[-1]["order"] == (1 if parent else 2)
    assert payload["routes"][0]["page_id"] == 11
    assert payload["routes"][1]["children"][0]["transition"] == {"effect": "push", "duration_ms": 600}
    assert baseline == ROUTE_TREE
    assert "effective_slideshow" not in str(payload)


@pytest.mark.parametrize("extra", [["--route", "cover"], ["--route", "details", "--parent", "missing"],
                                 ["--route", "details", "--parent", "cover"], ["--route", "/invalid"]])
def test_route_add_rejects_invalid_or_conflicting_target(extra):
    """重复路径、无效父节点和非相对路由都不能触发整树写回。"""

    client = MagicMock()
    client.get.return_value = deepcopy(ROUTE_TREE)
    with patch("wp.commands.project_route_add.get_client", return_value=client):
        result = CliRunner().invoke(main, ["project", "route", "add", "7", "--page-id", "13", *extra])
    assert result.exit_code != 0
    client.put.assert_not_called()


def test_route_add_repeated_desired_binding_does_not_write():
    """网络重试时已存在的相同挂载作为成功返回，不重复新增或覆盖其它节点。"""

    client = MagicMock()
    client.get.return_value = deepcopy(ROUTE_TREE)
    with patch("wp.commands.project_route_add.get_client", return_value=client):
        result = CliRunner().invoke(main, ["--json", "project", "route", "add", "7", "--page-id", "11", "--route", "cover"])
    assert result.exit_code == 0, result.output
    client.put.assert_not_called()


def test_route_add_honors_explicit_order_and_hidden():
    """明确给出的顺序和隐藏状态应进入新增节点。"""

    client = MagicMock()
    client.get.return_value = {"routes": []}
    client.put.return_value = {"routes": []}
    with patch("wp.commands.project_route_add.get_client", return_value=client):
        result = CliRunner().invoke(main, ["project", "route", "add", "7", "--page-id", "11",
                                          "--route", "cover", "--order", "5", "--hidden"])
    assert result.exit_code == 0, result.output
    node = client.put.call_args.kwargs["json_data"]["routes"][0]
    assert node["order"] == 5 and node["hidden"] is True
