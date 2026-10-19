"""文件功能：验证 Doctor 的 Skill 原因、版本、修复范围及窄终端完整输出。"""

from dataclasses import replace

from rich.console import Console
import pytest

from wp.skills.catalog import get_bundled_skill
from wp.skills.diagnostics import print_skill_details, skill_diagnostic
from wp.skills.installer import install_skill
from wp.skills.targets import plan_targets


def test_outdated_skill_diagnostic_has_version_and_scoped_repair(monkeypatch, tmp_path):
    """真实旧版安装应显示版本差异，并给出指向原安装范围的同步命令。"""

    target = plan_targets("web-presentation", scope="global", home_dir=tmp_path)[0]
    skill = get_bundled_skill("web-presentation")
    install_skill(replace(skill, version="0.1.0"), target)
    monkeypatch.setattr("wp.skills.diagnostics.plan_targets", lambda *args, **kwargs: [target] if kwargs["scope"] == "global" else [])
    result = skill_diagnostic()
    detail = result["targets"][0]
    assert result["status"] == "warning"
    assert detail["status"] == "outdated"
    assert detail["installed_version"] == "0.1.0"
    assert detail["bundled_version"] == skill.version
    assert detail["action"] == "wp skill install web-presentation --scope global"


def test_missing_skill_diagnostic_provides_install_command(monkeypatch, tmp_path):
    """没有任何安装时仍提供清楚的原因与可执行安装入口。"""

    target = plan_targets("web-presentation", scope="global", home_dir=tmp_path)[0]
    monkeypatch.setattr("wp.skills.diagnostics.plan_targets", lambda *args, **kwargs: [target])
    result = skill_diagnostic()
    assert result["targets"][0]["status"] == "missing"
    assert "尚未安装" in result["value"]
    assert "install" in result["targets"][0]["action"]


@pytest.mark.parametrize("status", ["modified", "unmanaged", "incompatible", "newer"])
def test_custom_or_incompatible_install_is_not_blindly_replaced(monkeypatch, tmp_path, status):
    """自定义或不兼容安装只建议检查，不引导 force 覆盖或降级。"""

    target = plan_targets("web-presentation", scope="project", project_dir=tmp_path)[0]
    target.path.mkdir(parents=True)
    monkeypatch.setattr("wp.skills.diagnostics.plan_targets", lambda *args, **kwargs: [target] if kwargs["scope"] == "project" else [])
    monkeypatch.setattr("wp.skills.diagnostics.inspect_target", lambda *args: {
        "status": status, "scope": "project", "path": str(target.path), "bundled_version": "1.4.2",
    })
    result = skill_diagnostic()
    action = result["targets"][0]["action"]
    assert "skill status" in action and "--project-dir" in action
    assert "--force" not in action and "install" not in action


def test_skill_details_are_not_ellipsized_in_narrow_terminal(monkeypatch, tmp_path):
    """长路径和修复命令在窄终端折行输出，不能被表格省略。"""

    console = Console(width=45, record=True, force_terminal=False)
    monkeypatch.setattr("wp.skills.diagnostics.console", console)
    path = str(tmp_path / "long-project-directory" / ".agents/skills/web-presentation")
    print_skill_details([{"check": "Agent Skill", "targets": [{
        "status": "outdated", "reason": "安装版本过期", "path": path,
        "installed_version": "1.4.0", "bundled_version": "1.4.2",
        "action": "wp skill install web-presentation --scope global",
    }]}])
    text = console.export_text()
    compact = "".join(text.split())
    assert "安装版本过期" in text
    assert "".join(path.split()) in compact
    assert "wpskillinstallweb-presentation--scopeglobal" in compact
    assert "…" not in text
