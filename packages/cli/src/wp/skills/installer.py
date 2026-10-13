"""文件功能：安全安装、检查、卸载和导出 CLI 内置 Skill。"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid
import zipfile

from wp import __version__
from wp.skills.catalog import (
    INSTALL_MARKER,
    BundledSkill,
    hash_skill_directory,
    parse_semver,
    version_satisfies,
)
from wp.skills.targets import SkillTarget


class SkillInstallError(RuntimeError):
    """表示安装目标冲突、越界或版本不允许等可预期错误。"""


def _target_payload(target: SkillTarget) -> dict[str, Any]:
    """生成终端与 JSON 输出共用的目标基础字段。"""

    return {
        "path": str(target.path),
        "scope": target.scope,
    }


def _validate_target(target: SkillTarget) -> None:
    """确保目标位于选定根目录内，且目标本身不是符号链接。"""

    base = target.base.resolve()
    parent = target.path.parent.resolve()
    if not parent.is_relative_to(base):
        raise SkillInstallError(f"Skill 目标越过安装根目录: {target.path}")
    if target.path.is_symlink():
        raise SkillInstallError(f"拒绝操作符号链接 Skill 目录: {target.path}")


def _read_marker(path: Path) -> dict[str, Any] | None:
    """读取 wp 安装标记；不存在或损坏时视为未受管理。"""

    marker_path = path / INSTALL_MARKER
    if not marker_path.is_file():
        return None
    try:
        value = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    required = {
        "manager",
        "skill_name",
        "skill_version",
        "bundled_cli_version",
        "requires_cli",
        "content_sha256",
    }
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("manager") != "web-presentation-cli"
        or not required.issubset(value)
    ):
        return None
    return value


def inspect_target(skill: BundledSkill, target: SkillTarget) -> dict[str, Any]:
    """检查目标的管理状态、内容完整性、版本新旧和 CLI 兼容性。"""

    result = _target_payload(target)
    result.update({"skill": skill.name, "bundled_version": skill.version})
    _validate_target(target)
    if not target.path.exists():
        return {**result, "status": "missing"}
    if not target.path.is_dir():
        return {**result, "status": "unmanaged", "reason": "目标不是目录"}

    marker = _read_marker(target.path)
    if marker is None or marker.get("skill_name") != skill.name:
        return {**result, "status": "unmanaged", "reason": "缺少有效的 wp 安装标记"}

    installed_version = str(marker.get("skill_version") or "")
    installed_hash = str(marker.get("content_sha256") or "")
    result["installed_version"] = installed_version
    try:
        actual_hash = hash_skill_directory(target.path)
    except OSError as exc:
        return {**result, "status": "modified", "reason": str(exc)}
    if not installed_hash or actual_hash != installed_hash:
        return {**result, "status": "modified", "content_sha256": actual_hash}

    requirement = str(marker.get("requires_cli") or "")
    try:
        compatible = bool(requirement) and version_satisfies(__version__, requirement)
    except ValueError:
        compatible = False
    if not compatible:
        return {**result, "status": "incompatible", "requires_cli": requirement}

    try:
        installed_semver = parse_semver(installed_version)
        bundled_semver = parse_semver(skill.version)
    except ValueError:
        return {**result, "status": "unmanaged", "reason": "安装版本格式无效"}
    if installed_semver < bundled_semver or installed_hash != skill.content_sha256:
        status = "outdated"
    elif installed_semver > bundled_semver:
        status = "newer"
    else:
        status = "up_to_date"
    return {**result, "status": status, "content_sha256": actual_hash}


def _write_staging(skill: BundledSkill, target: SkillTarget) -> Path:
    """在目标同级目录创建完整 staging 副本并写入管理标记。"""

    target.path.parent.mkdir(parents=True, exist_ok=True)
    staging = target.path.parent / f".{target.path.name}.staging.{uuid.uuid4().hex}"
    try:
        shutil.copytree(skill.root, staging, copy_function=shutil.copy2)
        marker = {
            "schema_version": 1,
            "manager": "web-presentation-cli",
            "skill_name": skill.name,
            "skill_version": skill.version,
            "bundled_cli_version": __version__,
            "requires_cli": skill.requires_cli,
            "content_sha256": skill.content_sha256,
            "installed_at": datetime.now(UTC).isoformat(),
        }
        (staging / INSTALL_MARKER).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return staging


def _backup_path(target: Path) -> Path:
    """生成不会覆盖已有内容的同级时间戳备份路径。"""

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return target.with_name(f".{target.name}.backup.{timestamp}")


def install_skill(
    skill: BundledSkill,
    target: SkillTarget,
    *,
    dry_run: bool = False,
    force: bool = False,
    allow_downgrade: bool = False,
) -> dict[str, Any]:
    """幂等安装或升级 Skill；异常目标只在 force 下备份后替换。"""

    current = inspect_target(skill, target)
    status = current["status"]
    if status == "up_to_date":
        return {**current, "action": "unchanged"}
    installed_version = current.get("installed_version")
    try:
        is_downgrade = bool(installed_version) and parse_semver(str(installed_version)) > parse_semver(
            skill.version
        )
    except ValueError:
        is_downgrade = False
    if is_downgrade and not allow_downgrade:
        raise SkillInstallError(f"已安装 Skill 新于 CLI 内置版本，拒绝降级: {target.path}")
    if status in {"modified", "unmanaged"} and not force:
        raise SkillInstallError(f"目标包含未受管理或已修改的内容，请使用 --force: {target.path}")

    action = "install" if status == "missing" else "downgrade" if is_downgrade else "update"
    if dry_run:
        return {**current, "action": f"would_{action}"}

    staging = _write_staging(skill, target)
    moved_target: Path | None = None
    retained_backup = force and target.path.exists()
    try:
        if target.path.exists():
            moved_target = _backup_path(target.path)
            os.replace(target.path, moved_target)
        os.replace(staging, target.path)
        installed = inspect_target(skill, target)
        if installed["status"] != "up_to_date":
            raise SkillInstallError(f"安装后完整性校验失败: {target.path}")
    except BaseException:
        if target.path.exists() and not target.path.is_symlink():
            shutil.rmtree(target.path, ignore_errors=True)
        if moved_target is not None and moved_target.exists():
            os.replace(moved_target, target.path)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    if moved_target is not None and moved_target.exists() and not retained_backup:
        shutil.rmtree(moved_target)

    installed["action"] = action
    if retained_backup and moved_target is not None:
        installed["backup_path"] = str(moved_target)
    return installed


def uninstall_skill(skill: BundledSkill, target: SkillTarget, *, force: bool = False) -> dict[str, Any]:
    """卸载受管理且未修改的 Skill；强制处理异常目标时保留备份。"""

    current = inspect_target(skill, target)
    status = current["status"]
    if status == "missing":
        return {**current, "action": "unchanged"}
    abnormal = status in {"modified", "unmanaged"}
    if abnormal and not force:
        raise SkillInstallError(f"拒绝卸载未受管理或已修改的 Skill，请使用 --force: {target.path}")
    if force and abnormal:
        backup = _backup_path(target.path)
        os.replace(target.path, backup)
        return {**current, "action": "uninstalled_with_backup", "backup_path": str(backup)}

    temporary = target.path.with_name(f".{target.path.name}.removing.{uuid.uuid4().hex}")
    os.replace(target.path, temporary)
    try:
        shutil.rmtree(temporary)
    except BaseException:
        os.replace(temporary, target.path)
        raise
    return {**current, "action": "uninstalled"}


def export_skill(skill: BundledSkill, output: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    """导出根目录即 SKILL.md 的可重复 ZIP，不包含 wp 安装标记。"""

    destination = (output or Path.cwd() / f"{skill.name}-{skill.version}.zip").expanduser().resolve()
    if destination.exists() and not force:
        raise SkillInstallError(f"导出文件已存在，请使用 --force: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(temporary_handle)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            files = sorted(
                (
                    (path.relative_to(skill.root).as_posix(), path)
                    for path in skill.root.rglob("*")
                    if path.is_file() and path.name != INSTALL_MARKER
                ),
                key=lambda item: item[0],
            )
            for relative, path in files:
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100644 & 0xFFFF) << 16
                archive.writestr(info, path.read_bytes())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "skill": skill.name,
        "skill_version": skill.version,
        "path": str(destination),
        "content_sha256": skill.content_sha256,
        "action": "exported",
    }
