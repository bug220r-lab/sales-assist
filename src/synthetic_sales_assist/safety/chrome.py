"""Validation for a future least-privilege Chrome Manifest V3 extension.

Milestone 0 does not ship an extension.  This module instead establishes the closed
permission policy that a future manifest must pass.  Validation is structural and has
no browser or filesystem side effects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast


ALLOWED_CHROME_HOST_PATTERNS = frozenset(
    {
        "http://127.0.0.1/*",
        "http://localhost/*",
    }
)

# The extraction design uses declarative content-script matches and therefore needs no
# Chrome API permission.  Keeping this allowlist empty prevents a later manifest from
# silently acquiring mutation, interception, browsing-history, generic-tab, or native
# integration capability.
ALLOWED_CHROME_API_PERMISSIONS: frozenset[str] = frozenset()

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
    patterns: tuple[str, ...], *, path: str, require_nonempty: bool = False
) -> None:
    if require_nonempty and not patterns:
        raise ChromePermissionViolation(f"{path} must not be empty")
    unexpected = sorted(set(patterns) - ALLOWED_CHROME_HOST_PATTERNS)
    if unexpected:
        raise ChromePermissionViolation(
            f"{path} contains a prohibited Chrome host pattern"
        )


def _validate_content_scripts(
    manifest: Mapping[str, object],
) -> list[tuple[str, tuple[str, ...]]]:
    surfaces: list[tuple[str, tuple[str, ...]]] = []
    for index, script in enumerate(
        _object_array(manifest, "content_scripts", path="manifest")
    ):
        path = f"manifest.content_scripts[{index}]"
        matches = _string_array(script, "matches", path=path, required=True)
        _validate_host_patterns(matches, path=f"{path}.matches", require_nonempty=True)
        surfaces.append((f"content_scripts[{index}].matches", matches))

        excludes = _string_array(script, "exclude_matches", path=path)
        _validate_host_patterns(excludes, path=f"{path}.exclude_matches")
        if excludes:
            surfaces.append((f"content_scripts[{index}].exclude_matches", excludes))

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
        if "world" in script and script["world"] != "ISOLATED":
            raise ChromePermissionViolation(f"{path}.world must be ISOLATED")
    return surfaces


def _validate_web_accessible_resources(
    manifest: Mapping[str, object],
) -> list[tuple[str, tuple[str, ...]]]:
    surfaces: list[tuple[str, tuple[str, ...]]] = []
    for index, resource in enumerate(
        _object_array(manifest, "web_accessible_resources", path="manifest")
    ):
        path = f"manifest.web_accessible_resources[{index}]"
        matches = _string_array(resource, "matches", path=path, required=True)
        _validate_host_patterns(matches, path=f"{path}.matches", require_nonempty=True)
        surfaces.append((f"web_accessible_resources[{index}].matches", matches))
        if _string_array(resource, "extension_ids", path=path):
            raise ChromePermissionViolation(f"{path}.extension_ids is prohibited")
    return surfaces


def _validate_externally_connectable(
    manifest: Mapping[str, object],
) -> list[tuple[str, tuple[str, ...]]]:
    if "externally_connectable" not in manifest:
        return []
    external = _require_mapping(
        manifest["externally_connectable"], path="manifest.externally_connectable"
    )
    matches = _string_array(external, "matches", path="manifest.externally_connectable")
    _validate_host_patterns(matches, path="manifest.externally_connectable.matches")
    if _string_array(external, "ids", path="manifest.externally_connectable"):
        raise ChromePermissionViolation("manifest.externally_connectable.ids is prohibited")
    if external.get("accepts_tls_channel_id") is True:
        raise ChromePermissionViolation(
            "manifest.externally_connectable.accepts_tls_channel_id must not be true"
        )
    if not matches:
        return []
    return [("externally_connectable.matches", matches)]


def validate_chrome_permissions(manifest: object) -> ChromePermissionInventory:
    """Validate every host/API permission surface in a future MV3 manifest.

    ``host_permissions`` must contain both and only the closed localhost patterns.
    Other match surfaces may use any non-empty subset of those patterns, but can never
    introduce a third pattern.  Chrome API permissions are deny-by-default.
    """

    candidate = _require_mapping(manifest, path="manifest")
    if candidate.get("manifest_version") != 3:
        raise ChromePermissionViolation("manifest.manifest_version must be exactly 3")

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
    _validate_host_patterns(
        optional_host_permissions, path="manifest.optional_host_permissions"
    )

    api_permissions = _string_array(candidate, "permissions", path="manifest")
    optional_api_permissions = _string_array(
        candidate, "optional_permissions", path="manifest"
    )
    for path, permissions in (
        ("manifest.permissions", api_permissions),
        ("manifest.optional_permissions", optional_api_permissions),
    ):
        unexpected = sorted(set(permissions) - ALLOWED_CHROME_API_PERMISSIONS)
        if unexpected:
            raise ChromePermissionViolation(
                f"{path} contains a prohibited Chrome API capability"
            )

    surfaces = _validate_content_scripts(candidate)
    surfaces.extend(_validate_web_accessible_resources(candidate))
    surfaces.extend(_validate_externally_connectable(candidate))

    inventory = ChromePermissionInventory(
        manifest_version=3,
        host_permissions=host_permissions,
        optional_host_permissions=optional_host_permissions,
        api_permissions=api_permissions,
        optional_api_permissions=optional_api_permissions,
        match_surfaces=tuple(surfaces),
    )
    if inventory.all_host_patterns != ALLOWED_CHROME_HOST_PATTERNS:
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
    "ALLOWED_CHROME_HOST_PATTERNS",
    "ChromePermissionInventory",
    "ChromePermissionViolation",
    "FORBIDDEN_PRIVILEGED_MANIFEST_KEYS",
    "is_chrome_permission_set_safe",
    "validate_chrome_manifest_permissions",
    "validate_chrome_permissions",
]
