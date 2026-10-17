"""文件功能：测试内置 Skill 的目标规划、安装生命周期、CLI 交互边界与 ZIP 导出。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import zipfile

from click.testing import CliRunner
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from wp.cli import main
from wp.skills.catalog import BundledSkill, get_bundled_skill, hash_skill_directory, version_satisfies
from wp.skills.installer import (
    SkillInstallError,
    export_skill,
    inspect_target,
    install_skill,
    uninstall_skill,
)
from wp.skills.targets import SkillTarget, plan_targets
import wp.skills.installer as skill_installer


def _target(tmp_path: Path) -> SkillTarget:
    """创建位于临时项目中的 .agents/skills 目标。"""

    return SkillTarget(
        path=tmp_path / ".agents" / "skills" / "web-presentation",
        base=tmp_path,
        scope="project",
    )


def test_plan_targets_resolves_project_and_global_agents_directory(tmp_path: Path) -> None:
    """项目与全局范围都只应生成单一的 .agents/skills 安装目标。"""

    project_targets = plan_targets(
        "web-presentation",
        scope="project",
        project_dir=tmp_path,
    )
    assert len(project_targets) == 1
    assert project_targets[0].path == tmp_path / ".agents" / "skills" / "web-presentation"
    assert project_targets[0].scope == "project"

    home = tmp_path / "home"
    home.mkdir()
    global_targets = plan_targets(
        "web-presentation",
        scope="global",
        home_dir=home,
    )
    assert len(global_targets) == 1
    assert global_targets[0].path == home / ".agents" / "skills" / "web-presentation"
    assert global_targets[0].scope == "global"


def test_plan_targets_rejects_invalid_scope(tmp_path: Path) -> None:
    """未知的安装范围应立即抛出 ValueError。"""

    with pytest.raises(ValueError, match="不支持的安装范围"):
        plan_targets(
            "web-presentation",
            scope="invalid",
            project_dir=tmp_path,
        )


def test_bundled_skill_minimum_cli_covers_model3d_commands() -> None:
    """Skill 已使用 0.3.2 才提供的三维资源命令，不能声明兼容更早版本。"""

    skill = get_bundled_skill("web-presentation")
    assert version_satisfies("0.3.1", skill.requires_cli) is False
    assert version_satisfies("0.3.2", skill.requires_cli) is True


def test_install_status_and_uninstall_lifecycle(tmp_path: Path) -> None:
    """首次安装、重复安装、状态检查和正常卸载应形成幂等闭环。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)

    installed = install_skill(skill, target)
    assert installed["action"] == "install"
    assert installed["status"] == "up_to_date"
    assert (target.path / "SKILL.md").is_file()
    assert (target.path / ".wp-install.json").is_file()

    repeated = install_skill(skill, target)
    assert repeated["action"] == "unchanged"
    assert inspect_target(skill, target)["status"] == "up_to_date"

    removed = uninstall_skill(skill, target)
    assert removed["action"] == "uninstalled"
    assert not target.path.exists()


def test_modified_install_requires_force_and_retains_backup(tmp_path: Path) -> None:
    """用户修改后的目录必须拒绝普通升级，强制安装时保留原目录备份。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)
    install_skill(skill, target)
    (target.path / "SKILL.md").write_text("用户修改", encoding="utf-8")

    assert inspect_target(skill, target)["status"] == "modified"
    with pytest.raises(SkillInstallError, match="--force"):
        install_skill(skill, target)

    result = install_skill(skill, target, force=True)
    backup = Path(result["backup_path"])
    assert result["status"] == "up_to_date"
    assert backup.is_dir()
    assert (backup / "SKILL.md").read_text(encoding="utf-8") == "用户修改"


def test_newer_install_requires_explicit_downgrade(tmp_path: Path) -> None:
    """已安装版本高于内置版本时必须显式允许降级。"""

    skill = get_bundled_skill("web-presentation")
    newer = BundledSkill(
        name=skill.name,
        version="2.0.0",
        requires_cli=skill.requires_cli,
        content_sha256=skill.content_sha256,
        root=skill.root,
    )
    target = _target(tmp_path)
    install_skill(newer, target)

    assert inspect_target(skill, target)["status"] == "newer"
    with pytest.raises(SkillInstallError, match="拒绝降级"):
        install_skill(skill, target)
    result = install_skill(skill, target, allow_downgrade=True)
    assert result["action"] == "downgrade"
    assert result["status"] == "up_to_date"


def test_incompatible_newer_install_still_requires_explicit_downgrade(tmp_path: Path) -> None:
    """即使旧标记对当前 CLI 不兼容，也不能绕过已安装版本的降级保护。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)
    install_skill(skill, target)
    marker_path = target.path / ".wp-install.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.update({"skill_version": "2.0.0", "requires_cli": ">=0.4.0,<0.5.0"})
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    assert inspect_target(skill, target)["status"] == "incompatible"
    with pytest.raises(SkillInstallError, match="拒绝降级"):
        install_skill(skill, target)


def test_failed_atomic_upgrade_restores_previous_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新目录替换失败时应恢复原安装，且不留下 staging 目录。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)
    install_skill(skill, target)
    (target.path / "local-change.txt").write_text("保留", encoding="utf-8")
    original_marker = (target.path / ".wp-install.json").read_bytes()
    real_replace = os.replace
    call_count = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        """仅让 staging 写入目标的步骤失败，使回滚路径得到覆盖。"""

        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("模拟原子替换失败")
        real_replace(source, destination)

    monkeypatch.setattr(skill_installer.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="模拟原子替换失败"):
        install_skill(skill, target, force=True)

    assert (target.path / ".wp-install.json").read_bytes() == original_marker
    assert (target.path / "local-change.txt").read_text(encoding="utf-8") == "保留"
    assert not list(target.path.parent.glob(".web-presentation.staging.*"))


def test_damaged_marker_is_unmanaged(tmp_path: Path) -> None:
    """缺少 schema 的伪标记不能让用户目录被当作受管理安装。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)
    target.path.mkdir(parents=True)
    (target.path / ".wp-install.json").write_text(
        json.dumps({"manager": "web-presentation-cli", "skill_name": skill.name}),
        encoding="utf-8",
    )

    assert inspect_target(skill, target)["status"] == "unmanaged"


def test_force_uninstall_of_unmanaged_target_keeps_backup(tmp_path: Path) -> None:
    """强制卸载未受管理目录时只移走并保留备份，不永久删除用户内容。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)
    target.path.mkdir(parents=True)
    (target.path / "custom.txt").write_text("保留", encoding="utf-8")

    with pytest.raises(SkillInstallError, match="--force"):
        uninstall_skill(skill, target)
    result = uninstall_skill(skill, target, force=True)
    backup = Path(result["backup_path"])
    assert result["action"] == "uninstalled_with_backup"
    assert (backup / "custom.txt").read_text(encoding="utf-8") == "保留"


def test_export_is_reproducible_and_has_skill_at_archive_root(tmp_path: Path) -> None:
    """通用 ZIP 应可重复构建，并在压缩包根目录暴露标准 SKILL.md。"""

    skill = get_bundled_skill("web-presentation")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    export_skill(skill, first)
    export_skill(skill, second)

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert "SKILL.md" in names
        assert ".wp-install.json" not in names
        assert any(name.startswith("references/") for name in names)


def test_cli_requires_explicit_selection_when_noninteractive() -> None:
    """非交互模式缺少 scope 时应返回用法错误而不是等待输入。"""

    result = CliRunner().invoke(main, ["skill", "status"])

    assert result.exit_code == 2
    assert "缺少 --scope" in result.output


def test_cli_rejects_removed_agent_option() -> None:
    """命令不应再接受 --agent 参数。"""

    result = CliRunner().invoke(main, ["skill", "status", "--scope", "project", "--agent", "codex"])

    assert result.exit_code == 2
    assert "No such option" in result.output
    assert "--agent" in result.output


def test_interactive_scope_selection_uses_agents_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """交互界面只需一步选择范围，直接指向 .agents/skills 目录。"""

    monkeypatch.setattr("click.testing._NamedTextIOWrapper.isatty", lambda _stream: True)
    result = CliRunner().invoke(main, ["skill", "status"], input="2\n")

    assert result.exit_code == 0, result.output
    assert "请选择检查范围" in result.output
    assert "1) 全局：用户目录下的 ~/.agents/skills" in result.output
    assert "2) 项目：项目根目录下的 .agents/skills" in result.output
    assert "请选择 Agent" not in result.output


def test_interactive_global_selection_identifies_home_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全局交互选择应只询问范围并检查用户目录下的 ~/.agents/skills。"""

    monkeypatch.setattr("click.testing._NamedTextIOWrapper.isatty", lambda _stream: True)
    result = CliRunner().invoke(main, ["skill", "status"], input="1\n")

    assert result.exit_code == 0, result.output
    assert "1) 全局：用户目录下的 ~/.agents/skills" in result.output
    assert "global" in result.output


def test_interactive_uninstall_uses_uninstall_specific_wording(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """卸载交互只选择范围并确认目标目录与保护规则。"""

    monkeypatch.setattr("click.testing._NamedTextIOWrapper.isatty", lambda _stream: True)
    result = CliRunner().invoke(
        main,
        ["skill", "uninstall", "--project-dir", str(tmp_path)],
        input="2\ny\n",
    )

    assert result.exit_code == 0, result.output
    assert "请选择卸载范围" in result.output
    assert "受管理且未修改的安装将被删除" in result.output
    assert "用户修改或未受管理的目录将拒绝卸载" in result.output
    assert "请选择安装范围" not in result.output
    assert "请选择 Agent" not in result.output


def test_cli_project_json_lifecycle(tmp_path: Path) -> None:
    """CLI 应支持项目级 JSON 安装、状态和显式确认卸载。"""

    runner = CliRunner()
    common = [
        "--scope",
        "project",
        "--project-dir",
        str(tmp_path),
        "--json",
    ]

    installed = runner.invoke(main, ["skill", "install", *common])
    assert installed.exit_code == 0, installed.output
    targets = json.loads(installed.output)["targets"]
    assert len(targets) == 1
    assert "agents" not in targets[0]

    status = runner.invoke(main, ["skill", "status", *common])
    assert status.exit_code == 0, status.output
    assert {item["status"] for item in json.loads(status.output)["targets"]} == {"up_to_date"}

    uninstalled = runner.invoke(main, ["skill", "uninstall", *common, "--yes"])
    assert uninstalled.exit_code == 0, uninstalled.output
    assert {item["action"] for item in json.loads(uninstalled.output)["targets"]} == {"uninstalled"}


def test_installed_content_hash_excludes_management_marker(tmp_path: Path) -> None:
    """管理标记不应改变 Skill 标准内容的摘要。"""

    skill = get_bundled_skill("web-presentation")
    target = _target(tmp_path)
    install_skill(skill, target)

    assert hash_skill_directory(target.path) == skill.content_sha256
