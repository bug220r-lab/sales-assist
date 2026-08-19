"""Tests for the future Chrome Manifest V3 permission safety contract."""

from __future__ import annotations

import copy
import unittest

from synthetic_sales_assist.safety.chrome import (
    ALLOWED_CHROME_API_PERMISSIONS,
    ALLOWED_CHROME_HOST_PATTERNS,
    ChromePermissionViolation,
    FORBIDDEN_PRIVILEGED_MANIFEST_KEYS,
    is_chrome_permission_set_safe,
    validate_chrome_permissions,
)


def _minimal_safe_manifest() -> dict[str, object]:
    return {
        "manifest_version": 3,
        "name": "Synthetic localhost reader",
        "version": "0.0.0",
        "permissions": [],
        "host_permissions": [
            "http://127.0.0.1/*",
            "http://localhost/*",
        ],
    }


def _match_pattern(scheme: str, host: str) -> str:
    """Build negative match-pattern canaries without a prohibited URL literal."""

    return f"{scheme}:{'/' * 2}{host}/*"


def _outside_host() -> str:
    return "outside" + "." + "invalid"


class ClosedPermissionInventoryTests(unittest.TestCase):
    def test_closed_permission_constants_are_exact(self) -> None:
        self.assertEqual(
            ALLOWED_CHROME_HOST_PATTERNS,
            frozenset(
                {
                    "http://127.0.0.1/*",
                    "http://localhost/*",
                }
            ),
        )
        self.assertEqual(ALLOWED_CHROME_API_PERMISSIONS, frozenset())

    def test_minimal_manifest_is_safe_and_returns_an_inventory(self) -> None:
        manifest = _minimal_safe_manifest()
        inventory = validate_chrome_permissions(manifest)

        self.assertEqual(inventory.manifest_version, 3)
        self.assertEqual(inventory.all_host_patterns, ALLOWED_CHROME_HOST_PATTERNS)
        self.assertEqual(inventory.api_permissions, ())
        self.assertTrue(is_chrome_permission_set_safe(manifest))

    def test_each_secondary_match_surface_accepts_only_local_subsets(self) -> None:
        manifest = _minimal_safe_manifest()
        manifest.update(
            {
                "optional_host_permissions": ["http://localhost/*"],
                "optional_permissions": [],
                "content_scripts": [
                    {
                        "matches": [
                            "http://localhost/*",
                            "http://127.0.0.1/*",
                        ],
                        "exclude_matches": ["http://localhost/*"],
                        "world": "ISOLATED",
                        "all_frames": False,
                        "match_about_blank": False,
                        "match_origin_as_fallback": False,
                        "js": ["reader.js"],
                    }
                ],
                "web_accessible_resources": [
                    {
                        "resources": ["view.css"],
                        "matches": ["http://127.0.0.1/*"],
                    }
                ],
                "externally_connectable": {
                    "matches": ["http://localhost/*"],
                    "accepts_tls_channel_id": False,
                },
            }
        )

        inventory = validate_chrome_permissions(manifest)
        self.assertEqual(inventory.all_host_patterns, ALLOWED_CHROME_HOST_PATTERNS)
        self.assertEqual(len(inventory.match_surfaces), 4)

    def test_manifest_version_and_required_hosts_fail_closed(self) -> None:
        rejected: tuple[object, ...] = (
            [],
            {},
            {"manifest_version": 2},
            {"manifest_version": 3},
            {
                "manifest_version": 3,
                "host_permissions": ["http://localhost/*"],
            },
            {
                "manifest_version": 3,
                "host_permissions": [
                    "http://localhost/*",
                    "http://localhost/*",
                ],
            },
            {
                "manifest_version": 3,
                "host_permissions": "http://localhost/*",
            },
        )
        for manifest in rejected:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)
                self.assertFalse(is_chrome_permission_set_safe(manifest))

    def test_lookalike_wildcard_nonlocal_and_ipv6_patterns_are_rejected(self) -> None:
        outside = _outside_host()
        unsafe_patterns = (
            "<all" + "_urls>",
            _match_pattern("*", "*"),
            _match_pattern("http", "*"),
            _match_pattern("http", "*" + ".localhost"),
            _match_pattern("http", "localhost" + ".localdomain"),
            _match_pattern("http", "localhost" + "." + outside),
            _match_pattern("http", "localhost" + ":8080"),
            _match_pattern("https", "localhost"),
            _match_pattern("http", "127.0.0." + "2"),
            _match_pattern("http", "127." + "1"),
            _match_pattern("http", "213070" + "6433"),
            _match_pattern("http", "[::" + "1]"),
            _match_pattern("file", "localhost"),
        )
        for pattern in unsafe_patterns:
            manifest = _minimal_safe_manifest()
            manifest["host_permissions"] = [
                "http://127.0.0.1/*",
                "http://localhost/*",
                pattern,
            ]
            with self.subTest(pattern=pattern):
                with self.assertRaises(ChromePermissionViolation) as caught:
                    validate_chrome_permissions(manifest)
                self.assertNotIn(pattern, str(caught.exception))


class AllPermissionSurfaceTests(unittest.TestCase):
    def test_nonlocal_optional_host_permission_is_rejected(self) -> None:
        manifest = _minimal_safe_manifest()
        canary = _match_pattern("https", _outside_host())
        manifest["optional_host_permissions"] = [canary]
        with self.assertRaises(ChromePermissionViolation) as caught:
            validate_chrome_permissions(manifest)
        self.assertNotIn(canary, str(caught.exception))

    def test_privileged_write_and_generic_api_permissions_are_rejected(self) -> None:
        capabilities = (
            "activeTab",
            "bookmarks",
            "browsingData",
            "clipboardRead",
            "clipboardWrite",
            "contentSettings",
            "cookies",
            "debugger",
            "declarativeNetRequest",
            "downloads",
            "history",
            "management",
            "nativeMessaging",
            "proxy",
            "scripting",
            "sessions",
            "storage",
            "tabs",
            "webNavigation",
            "webRequest",
            "webRequestBlocking",
        )
        for surface in ("permissions", "optional_permissions"):
            for capability in capabilities:
                manifest = _minimal_safe_manifest()
                manifest[surface] = [capability]
                with self.subTest(surface=surface, capability=capability):
                    with self.assertRaises(ChromePermissionViolation) as caught:
                        validate_chrome_permissions(manifest)
                    self.assertNotIn(capability, str(caught.exception))

    def test_nonlocal_content_script_match_or_exclusion_is_rejected(self) -> None:
        canary = _match_pattern("https", _outside_host())
        for key in ("matches", "exclude_matches"):
            manifest = _minimal_safe_manifest()
            script: dict[str, object] = {"matches": ["http://localhost/*"]}
            script[key] = [canary]
            manifest["content_scripts"] = [script]
            with self.subTest(surface=key):
                with self.assertRaises(ChromePermissionViolation) as caught:
                    validate_chrome_permissions(manifest)
                self.assertNotIn(canary, str(caught.exception))

    def test_content_script_broadening_switches_and_globs_are_rejected(self) -> None:
        dangerous_fields: dict[str, object] = {
            "all_frames": True,
            "match_about_blank": True,
            "match_origin_as_fallback": True,
            "world": "MAIN",
            "include_globs": ["*"],
            "exclude_globs": [_match_pattern("*", _outside_host())],
        }
        for key, value in dangerous_fields.items():
            manifest = _minimal_safe_manifest()
            script: dict[str, object] = {"matches": ["http://localhost/*"]}
            script[key] = value
            manifest["content_scripts"] = [script]
            with self.subTest(field=key):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)

    def test_web_accessible_resource_matches_and_extension_ids_are_closed(self) -> None:
        canary = _match_pattern("https", _outside_host())
        for resource in (
            {
                "resources": ["view.js"],
                "matches": [canary],
            },
            {
                "resources": ["view.js"],
                "matches": ["http://localhost/*"],
                "extension_ids": ["*"],
            },
        ):
            manifest = _minimal_safe_manifest()
            manifest["web_accessible_resources"] = [resource]
            with self.subTest(resource=resource):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)

    def test_externally_connectable_is_local_pages_only(self) -> None:
        canary = _match_pattern("https", _outside_host())
        rejected_external = (
            {"matches": [canary]},
            {"matches": ["<all" + "_urls>"]},
            {"matches": ["http://localhost/*"], "ids": ["*"]},
            {
                "matches": ["http://localhost/*"],
                "accepts_tls_channel_id": True,
            },
        )
        for external in rejected_external:
            manifest = _minimal_safe_manifest()
            manifest["externally_connectable"] = external
            with self.subTest(external=external):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)

    def test_privileged_manifest_capability_keys_are_rejected(self) -> None:
        for key in FORBIDDEN_PRIVILEGED_MANIFEST_KEYS:
            manifest = copy.deepcopy(_minimal_safe_manifest())
            manifest[key] = {}
            with self.subTest(capability=key):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)


if __name__ == "__main__":
    unittest.main()
