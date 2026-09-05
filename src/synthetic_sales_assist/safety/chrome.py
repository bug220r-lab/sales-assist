"""Closed validation for the localhost-only Milestone 6 Chrome extension.

Validation is structural and has no browser or filesystem side effects.  It admits
only the one API capability needed by the side panel and the two exact loopback match
patterns.  Every executable manifest resource must be a repository-relative path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import cast


ALLOWED_CHROME_HOST_PATTERNS = frozenset(
    {
        "http://127.0.0.1/*",
        "http://localhost/*",
    }
)
ALLOWED_CHROME_CONTENT_MATCH_PATTERNS = frozenset(
    {
        "http://127.0.0.1/orders/*",
        "http://127.0.0.1/interactions/*",
        "http://localhost/orders/*",
        "http://localhost/interactions/*",
    }
)

# Static content-script matching needs no API capability.  The single ``sidePanel``
# permission is required solely to expose the repository-owned local panel page.
ALLOWED_CHROME_API_PERMISSIONS = frozenset({"sidePanel"})
REQUIRED_CHROME_API_PERMISSIONS = ALLOWED_CHROME_API_PERMISSIONS
FORBIDDEN_CHROME_API_PERMISSIONS = frozenset(
    {
        "activeTab",
        "alarms",
        "bookmarks",
        "browsingData",
        "clipboardRead",
        "clipboardWrite",
        "contentSettings",
        "contextMenus",
        "cookies",
        "debugger",
        "declarativeContent",
        "declarativeNetRequest",
        "declarativeNetRequestFeedback",
        "declarativeNetRequestWithHostAccess",
        "desktopCapture",
        "downloads",
        "geolocation",
        "history",
        "idle",
        "management",
        "nativeMessaging",
        "notifications",
        "offscreen",
        "privacy",
        "proxy",
        "scripting",
        "search",
        "sessions",
        "storage",
        "tabCapture",
        "tabGroups",
        "tabs",
        "topSites",
        "unlimitedStorage",
        "webNavigation",
        "webRequest",
        "webRequestBlocking",
    }
)

EXTENSION_PAGE_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)
ALLOWED_MANIFEST_KEYS = frozenset(
    {
        "background",
        "content_scripts",
        "content_security_policy",
        "description",
        "host_permissions",
        "manifest_version",
        "minimum_chrome_version",
        "name",
        "permissions",
        "side_panel",
        "version",
    }
)
CHROME_EXTENSION_VERSION = "0.1.2"
CHROME_EXTENSION_NAME = "Synthetic Sales Assist Local Side Panel"
CHROME_EXTENSION_DESCRIPTION = (
    "Read-only localhost extraction and evaluation for reserved synthetic scenarios."
)
CONTENT_SCRIPT_RESOURCES = (
    "shared/canonical.js",
    "shared/contracts.js",
    "shared/origin.js",
    "shared/extraction.js",
    "content/content_script.js",
)
SERVICE_WORKER_PATH = "service_worker.js"
SIDE_PANEL_PATH = "side_panel/index.html"

# These manifest keys provide powerful browser, request-rewrite, authentication, file,
# or externally updated code surfaces independently of the normal permission arrays.
FORBIDDEN_PRIVILEGED_MANIFEST_KEYS = frozenset(
    {
        "chrome_settings_overrides",
        "chrome_url_overrides",
        "content_capabilities",
        "declarative_net_request",
        "devtools_page",
        "event_rules",
        "file_browser_handlers",
        "file_system_provider_capabilities",
        "input_components",
        "nacl_modules",
        "oauth2",
        "omnibox",
        "plugins",
        "sandbox",
        "tts_engine",
        "update_url",
        "vpn_provider",
        "webview",
        "externally_connectable",
        "web_accessible_resources",
    }
)


class ChromePermissionViolation(ValueError):
    """Raised when a future Chrome manifest exceeds the closed safety policy."""


@dataclass(frozen=True, slots=True)
class ChromePermissionInventory:
    """Immutable inventory returned after all permission surfaces pass validation."""

    manifest_version: int
    host_permissions: tuple[str, ...]
    optional_host_permissions: tuple[str, ...]
    api_permissions: tuple[str, ...]
    optional_api_permissions: tuple[str, ...]
    match_surfaces: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def all_host_patterns(self) -> frozenset[str]:
        patterns = set(self.host_permissions)
        patterns.update(self.optional_host_permissions)
        for _, surface_patterns in self.match_surfaces:
            patterns.update(surface_patterns)
        return frozenset(patterns)


def _require_mapping(value: object, *, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ChromePermissionViolation(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ChromePermissionViolation(f"{path} keys must be strings")
    return cast(Mapping[str, object], value)


def _string_array(
    container: Mapping[str, object],
    key: str,
    *,
    path: str,
    required: bool = False,
) -> tuple[str, ...]:
    if key not in container:
        if required:
            raise ChromePermissionViolation(f"{path}.{key} is required")
        return ()

    value = container[key]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ChromePermissionViolation(f"{path}.{key} must be an array of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ChromePermissionViolation(
                f"{path}.{key} must contain only non-empty strings"
            )
        items.append(item)
    result = tuple(items)
    if len(result) != len(set(result)):
        raise ChromePermissionViolation(f"{path}.{key} must not contain duplicates")
    return result


def _object_array(
    container: Mapping[str, object], key: str, *, path: str
) -> tuple[Mapping[str, object], ...]:
    if key not in container:
        return ()
    value = container[key]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ChromePermissionViolation(f"{path}.{key} must be an array of objects")
    return tuple(
        _require_mapping(item, path=f"{path}.{key}[{index}]")
        for index, item in enumerate(value)
    )


def _validate_host_patterns(
    patterns: tuple[str, ...],
    *,
    path: str,
    allowed: frozenset[str] = ALLOWED_CHROME_HOST_PATTERNS,
    require_nonempty: bool = False,
) -> None:
    if require_nonempty and not patterns:
        raise ChromePermissionViolation(f"{path} must not be empty")
    unexpected = sorted(set(patterns) - allowed)
    if unexpected:
        raise ChromePermissionViolation(
            f"{path} contains a prohibited Chrome host pattern"
        )


def _local_resource_path(value: object, *, path: str, suffix: str) -> str:
    if not isinstance(value, str) or not value:
        raise ChromePermissionViolation(f"{path} must be a non-empty local path")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or "\\" in value
        or ":" in value
        or "?" in value
        or "#" in value
        or candidate.suffix.lower() != suffix
    ):
        raise ChromePermissionViolation(f"{path} must be a bounded local {suffix} path")
    return value


def _validate_content_scripts(
    manifest: Mapping[str, object],
) -> list[tuple[str, tuple[str, ...]]]:
    surfaces: list[tuple[str, tuple[str, ...]]] = []
    for index, script in enumerate(
        _object_array(manifest, "content_scripts", path="manifest")
    ):
        path = f"manifest.content_scripts[{index}]"
        if set(script) != {"matches", "js", "run_at", "world"}:
            raise ChromePermissionViolation(
                f"{path} must contain only matches, js, run_at, and world"
            )
        matches = _string_array(script, "matches", path=path, required=True)
        _validate_host_patterns(
            matches,
            path=f"{path}.matches",
            allowed=ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
            require_nonempty=True,
        )
        if set(matches) != ALLOWED_CHROME_CONTENT_MATCH_PATTERNS or len(matches) != len(
            ALLOWED_CHROME_CONTENT_MATCH_PATTERNS
        ):
            raise ChromePermissionViolation(
                f"{path}.matches must contain exactly the four supported local detail routes"
            )
        surfaces.append((f"content_scripts[{index}].matches", matches))

        excludes = _string_array(script, "exclude_matches", path=path)
        if excludes:
            raise ChromePermissionViolation(f"{path}.exclude_matches must be empty")

        for glob_key in ("include_globs", "exclude_globs"):
            if _string_array(script, glob_key, path=path):
                raise ChromePermissionViolation(
                    f"{path}.{glob_key} is prohibited; use only the closed match patterns"
                )
        for broadening_flag in (
            "all_frames",
            "match_about_blank",
            "match_origin_as_fallback",
        ):
            if script.get(broadening_flag) is True:
                raise ChromePermissionViolation(f"{path}.{broadening_flag} must not be true")
        if script.get("world") != "ISOLATED":
            raise ChromePermissionViolation(f"{path}.world must be ISOLATED")
        javascript = _string_array(script, "js", path=path, required=True)
        if not javascript:
            raise ChromePermissionViolation(f"{path}.js must not be empty")
        for resource_index, resource in enumerate(javascript):
            _local_resource_path(
                resource,
                path=f"{path}.js[{resource_index}]",
                suffix=".js",
            )
        if javascript != CONTENT_SCRIPT_RESOURCES:
            raise ChromePermissionViolation(
                f"{path}.js must equal the exact ordered extraction runtime"
            )
        if _string_array(script, "css", path=path):
            raise ChromePermissionViolation(
                f"{path}.css is prohibited; content extraction has no page stylesheet"
            )
        if script.get("run_at") != "document_idle":
            raise ChromePermissionViolation(f"{path}.run_at must be document_idle")
    return surfaces


def _validate_extension_pages(manifest: Mapping[str, object]) -> None:
    csp = _require_mapping(
        manifest.get("content_security_policy"),
        path="manifest.content_security_policy",
    )
    if set(csp) != {"extension_pages"} or csp.get("extension_pages") != EXTENSION_PAGE_CSP:
        raise ChromePermissionViolation(
            "manifest.content_security_policy must contain only the exact extension CSP"
        )

    panel = _require_mapping(manifest.get("side_panel"), path="manifest.side_panel")
    if set(panel) != {"default_path"}:
        raise ChromePermissionViolation("manifest.side_panel must contain only default_path")
    panel_path = _local_resource_path(
        panel.get("default_path"),
        path="manifest.side_panel.default_path",
        suffix=".html",
    )
    if panel_path != SIDE_PANEL_PATH:
        raise ChromePermissionViolation("manifest.side_panel.default_path is not authorized")

    background = _require_mapping(manifest.get("background"), path="manifest.background")
    if set(background) != {"service_worker"}:
        raise ChromePermissionViolation("manifest.background must contain only service_worker")
    worker_path = _local_resource_path(
        background.get("service_worker"),
        path="manifest.background.service_worker",
        suffix=".js",
    )
    if worker_path != SERVICE_WORKER_PATH:
        raise ChromePermissionViolation("manifest.background.service_worker is not authorized")


def validate_chrome_permissions(manifest: object) -> ChromePermissionInventory:
    """Validate every host/API permission surface in a future MV3 manifest.

    ``host_permissions`` and static content-script matches must contain both and only
    the closed localhost patterns.  The API permission inventory is exactly
    ``sidePanel``; optional capability surfaces are empty.
    """

    candidate = _require_mapping(manifest, path="manifest")
    unexpected_keys = sorted(set(candidate) - ALLOWED_MANIFEST_KEYS)
    if unexpected_keys:
        raise ChromePermissionViolation("manifest contains an unapproved top-level member")
    required_keys = ALLOWED_MANIFEST_KEYS
    if set(candidate) != required_keys:
        raise ChromePermissionViolation("manifest is missing a required closed-contract member")
    if candidate.get("manifest_version") != 3:
        raise ChromePermissionViolation("manifest.manifest_version must be exactly 3")
    if candidate.get("name") != CHROME_EXTENSION_NAME:
        raise ChromePermissionViolation("manifest.name must equal the synthetic M6 name")
    if candidate.get("description") != CHROME_EXTENSION_DESCRIPTION:
        raise ChromePermissionViolation(
            "manifest.description must equal the synthetic M6 description"
        )
    version = candidate.get("version")
    if version != CHROME_EXTENSION_VERSION:
        raise ChromePermissionViolation("manifest.version must be exactly 0.1.2")
    if candidate.get("minimum_chrome_version") != "114":
        raise ChromePermissionViolation("manifest.minimum_chrome_version must be exactly 114")

    forbidden_keys = sorted(set(candidate) & FORBIDDEN_PRIVILEGED_MANIFEST_KEYS)
    if forbidden_keys:
        raise ChromePermissionViolation(
            "manifest contains a prohibited privileged capability"
        )

    host_permissions = _string_array(
        candidate, "host_permissions", path="manifest", required=True
    )
    if len(host_permissions) != len(ALLOWED_CHROME_HOST_PATTERNS) or set(
        host_permissions
    ) != ALLOWED_CHROME_HOST_PATTERNS:
        raise ChromePermissionViolation(
            "manifest.host_permissions must contain exactly "
            "http://127.0.0.1/* and http://localhost/*"
        )

    optional_host_permissions = _string_array(
        candidate, "optional_host_permissions", path="manifest"
    )
    if optional_host_permissions:
        raise ChromePermissionViolation("manifest.optional_host_permissions must be empty")

    api_permissions = _string_array(candidate, "permissions", path="manifest")
    optional_api_permissions = _string_array(
        candidate, "optional_permissions", path="manifest"
    )
    if set(api_permissions) != REQUIRED_CHROME_API_PERMISSIONS or len(api_permissions) != len(
        REQUIRED_CHROME_API_PERMISSIONS
    ):
        raise ChromePermissionViolation("manifest.permissions must contain exactly sidePanel")
    if optional_api_permissions:
        raise ChromePermissionViolation("manifest.optional_permissions must be empty")

    surfaces = _validate_content_scripts(candidate)
    if len(surfaces) != 1 or set(surfaces[0][1]) != ALLOWED_CHROME_CONTENT_MATCH_PATTERNS:
        raise ChromePermissionViolation(
            "manifest must contain one static content script with the exact detail routes"
        )
    _validate_extension_pages(candidate)

    inventory = ChromePermissionInventory(
        manifest_version=3,
        host_permissions=host_permissions,
        optional_host_permissions=optional_host_permissions,
        api_permissions=api_permissions,
        optional_api_permissions=optional_api_permissions,
        match_surfaces=tuple(surfaces),
    )
    if inventory.all_host_patterns != (
        ALLOWED_CHROME_HOST_PATTERNS | ALLOWED_CHROME_CONTENT_MATCH_PATTERNS
    ):
        # Defensive assertion: each secondary surface was checked above and the required
        # surface is exact, so this indicates a validator maintenance error.
        raise ChromePermissionViolation("Chrome host-pattern inventory is not closed")
    return inventory


def is_chrome_permission_set_safe(manifest: object) -> bool:
    """Return ``True`` only when :func:`validate_chrome_permissions` succeeds."""

    try:
        validate_chrome_permissions(manifest)
    except ChromePermissionViolation:
        return False
    return True


# An explicit long form helps call sites make clear that validation is manifest-level.
validate_chrome_manifest_permissions = validate_chrome_permissions


__all__ = [
    "ALLOWED_CHROME_API_PERMISSIONS",
    "ALLOWED_CHROME_CONTENT_MATCH_PATTERNS",
    "ALLOWED_CHROME_HOST_PATTERNS",
    "ALLOWED_MANIFEST_KEYS",
    "CHROME_EXTENSION_VERSION",
    "CHROME_EXTENSION_DESCRIPTION",
    "CHROME_EXTENSION_NAME",
    "CONTENT_SCRIPT_RESOURCES",
    "EXTENSION_PAGE_CSP",
    "FORBIDDEN_CHROME_API_PERMISSIONS",
    "REQUIRED_CHROME_API_PERMISSIONS",
    "SERVICE_WORKER_PATH",
    "SIDE_PANEL_PATH",
    "ChromePermissionInventory",
    "ChromePermissionViolation",
    "FORBIDDEN_PRIVILEGED_MANIFEST_KEYS",
    "is_chrome_permission_set_safe",
    "validate_chrome_manifest_permissions",
    "validate_chrome_permissions",
]
