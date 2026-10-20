"""文件功能：集中声明 CLI 各类稳定 JSON 返回的字段白名单。"""

from __future__ import annotations


PAGINATION_FIELDS = ("page", "page_size", "total")

PROJECT_LIST_FIELDS = (
    "id",
    "workspace_id",
    "workspace_name",
    "code",
    "name",
    "description",
    "is_system_managed",
    "status",
    "archived_at",
    "routed_page_count",
    "total_page_count",
    "first_page_title",
    "first_page_screenshot_url",
    "created_at",
    "updated_at",
)
PROJECT_DETAIL_FIELDS = PROJECT_LIST_FIELDS + (
    "page_width",
    "page_height",
    "base_font_size",
    "icon_default_stroke_width",
    "show_pdf_export_button",
    "menu_mode",
    "theme_key",
    "style_spec_markdown",
    "build_extra_assets_json",
    # 服务端实际返回时才保留；旧服务缺字段仍保持缺失，不补 null 或默认值。
    "slideshow",
    "audio_settings",
)

PAGE_LIST_FIELDS = (
    "id",
    "code",
    "current_version_no",
    "file_type",
    "title",
    "summary",
    "status",
    "workspace_id",
    "workspace_name",
    "project_id",
    "project_name",
    "screenshot_url",
    "screenshot_is_latest",
    "is_in_project_route",
)
PAGE_DETAIL_FIELDS = PAGE_LIST_FIELDS + (
    "speaker_notes",
    "screenshot_version_no",
    "screenshot_config_hash",
    "screenshot_viewport_width",
    "screenshot_viewport_height",
    "screenshot_updated_at",
    "route_bindings",
    "created_at",
    "updated_at",
)
PAGE_SOURCE_FIELDS = ("page_id", "code", "version_no", "file_type", "source_code")

COMPONENT_LIST_FIELDS = (
    "id",
    "workspace_id",
    "workspace_name",
    "code",
    "current_version_no",
    "draft_base_version_no",
    "has_unpublished_changes",
    "published_at",
    "file_type",
    "name",
    "import_name",
    "component_type",
    "summary",
    "status",
    "created_at",
    "updated_at",
    "import_path",
    "import_statement",
)
SUGGESTED_COMPONENT_FIELDS = (
    "id",
    "code",
    "name",
    "import_name",
    "component_type",
    "summary",
    "current_version_no",
    "available",
    "unavailable_reason",
    "import_path",
    "import_statement",
)
COMPONENT_DETAIL_FIELDS = COMPONENT_LIST_FIELDS + ("content", "preview_schema", "draft_hash")

ASSET_FIELDS = (
    "id",
    "workspace_id",
    "name",
    "file_name",
    "original_name",
    "description",
    "file_size",
    "file_hash",
    "content_type",
    "asset_type",
    "asset_role",
    "render_type",
    "tags",
    "analysis_metadata",
    "render_metadata",
    "approx_aspect_ratio",
    "approx_aspect_ratio_value",
    "aspect_ratio_source",
    "content_editable",
    "url",
    "font_config",
    "status",
    "archived_at",
    "archive_reason",
    "source_asset_id",
    "history_kind",
    "rename_block_reason",
    "delete_block_reason",
    "archive_block_reason",
    "archive_warning_reasons",
    "created_at",
    "updated_at",
)
# analysis_metadata 不在列表完整暴露；三维摘要由 output_profiles 按需派生。
ASSET_LIST_FIELDS = tuple(
    field
    for field in ASSET_FIELDS
    if field
    not in {
        "analysis_metadata",
        "render_metadata",
        "aspect_ratio_source",
        "archived_at",
        "archive_reason",
        "source_asset_id",
        "history_kind",
        "rename_block_reason",
        "delete_block_reason",
        "archive_block_reason",
        "archive_warning_reasons",
    }
)

THEME_FIELDS = (
    "id",
    "workspace_id",
    "key",
    "name",
    "description",
    "logo_asset_id",
    "invert_logo_asset_id",
    "project_icon_asset_id",
    "project_icon_name",
    "heading_font_family_id",
    "body_font_family_id",
    "code_font_family_id",
    "heading_font_label",
    "body_font_label",
    "code_font_label",
    "heading_font_preset",
    "body_font_preset",
    "code_font_preset",
    "palette",
    "logo_asset",
    "invert_logo_asset",
    "project_icon_asset",
    "heading_font_family",
    "body_font_family",
    "code_font_family",
    "resolved_theme_config_yaml",
    "created_at",
    "updated_at",
)

STYLE_FIELDS = (
    "id",
    "workspace_id",
    "key",
    "name",
    "description",
    "page_width",
    "page_height",
    "base_font_size",
    "icon_default_stroke_width",
    "show_pdf_export_button",
    "menu_mode",
    "theme_key",
    "style_spec_markdown",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
)

VALIDATION_FIELDS = (
    "entity_type",
    "entity_id",
    "mode",
    "valid",
    "summary",
    "errors",
    "warnings",
    "imports",
)

PREVIEW_FIELDS = (
    "preview_url",
    "artifact_id",
    "preview_kind",
    "entry_descriptor",
    "viewport_width",
    "viewport_height",
    "project_id",
    "workspace_id",
    "component_preview_mode",
    "component_source",
    "component_code",
    "component_version_no",
    "runtime_kit_component_name",
    "runtime_kit_manifest_version",
    "asset_id",
    "asset_name",
)

FONT_FACE_FIELDS = (
    "id",
    "workspace_id",
    "family_id",
    "family_name",
    "asset_id",
    "asset_name",
    "font_format",
    "font_weight",
    "font_style",
    "font_display",
    "status",
    "created_at",
    "updated_at",
)

FONT_FAMILY_FIELDS = (
    "id",
    "workspace_id",
    "name",
    "faces",
    "created_at",
    "updated_at",
)
