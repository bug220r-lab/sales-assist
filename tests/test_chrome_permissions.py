"""Exhaustive tests for the Milestone 6 Chrome MV3 safety contract."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from synthetic_sales_assist.safety.chrome import (
    ALLOWED_CHROME_API_PERMISSIONS,
    ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
    ALLOWED_CHROME_HOST_PATTERNS,
    ChromePermissionViolation,
    EXTENSION_PAGE_CSP,
    FORBIDDEN_CHROME_API_PERMISSIONS,
    FORBIDDEN_PRIVILEGED_MANIFEST_KEYS,
    is_chrome_permission_set_safe,
    validate_chrome_permissions,
)


def _minimal_safe_manifest() -> dict[str, object]:
    return {
        "manifest_version": 3,
        "name": "Synthetic Sales Assist Local Side Panel",
        "description": (
            "Read-only localhost extraction and evaluation for reserved synthetic scenarios."
        ),
        "version": "0.1.2",
        "minimum_chrome_version": "114",
        "permissions": ["sidePanel"],
        "host_permissions": [
            "http://127.0.0.1/*",
            "http://localhost/*",
        ],
        "background": {"service_worker": "service_worker.js"},
        "side_panel": {"default_path": "side_panel/index.html"},
        "content_security_policy": {"extension_pages": EXTENSION_PAGE_CSP},
        "content_scripts": [
            {
                "matches": [
                    "http://127.0.0.1/orders/*",
                    "http://127.0.0.1/interactions/*",
                    "http://localhost/orders/*",
                    "http://localhost/interactions/*",
                ],
                "js": [
                    "shared/canonical.js",
                    "shared/contracts.js",
                    "shared/origin.js",
                    "shared/extraction.js",
                    "content/content_script.js",
                ],
                "run_at": "document_idle",
                "world": "ISOLATED",
            }
        ],
    }


def _match_pattern(scheme: str, host: str) -> str:
    """Build negative match-pattern canaries without a prohibited URL literal."""

    return f"{scheme}:{'/' * 2}{host}/*"


def _outside_host() -> str:
    return "outside" + "." + "invalid"


ROOT = Path(__file__).resolve().parents[1]


class ClosedPermissionInventoryTests(unittest.TestCase):
    def test_committed_manifest_is_the_exact_closed_m6_inventory(self) -> None:
        manifest = json.loads(
            (ROOT / "chrome_extension" / "manifest.json").read_text(encoding="utf-8")
        )
        inventory = validate_chrome_permissions(manifest)
        self.assertEqual(inventory.api_permissions, ("sidePanel",))
        self.assertEqual(set(inventory.host_permissions), ALLOWED_CHROME_HOST_PATTERNS)
        self.assertEqual(
            set(inventory.match_surfaces[0][1]),
            ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
        )
        self.assertEqual(
            manifest["content_security_policy"]["extension_pages"],
            EXTENSION_PAGE_CSP,
        )

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
        self.assertEqual(ALLOWED_CHROME_API_PERMISSIONS, frozenset({"sidePanel"}))
        self.assertFalse(
            ALLOWED_CHROME_API_PERMISSIONS & FORBIDDEN_CHROME_API_PERMISSIONS
        )
        self.assertTrue(
            {
                "clipboardWrite",
                "cookies",
                "debugger",
                "downloads",
                "nativeMessaging",
                "storage",
                "tabs",
                "webRequest",
                "webRequestBlocking",
            }.issubset(FORBIDDEN_CHROME_API_PERMISSIONS)
        )
        self.assertEqual(
            ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
            frozenset(
                {
                    "http://127.0.0.1/orders/*",
                    "http://127.0.0.1/interactions/*",
                    "http://localhost/orders/*",
                    "http://localhost/interactions/*",
                }
            ),
        )
        self.assertEqual(
            EXTENSION_PAGE_CSP,
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'none'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'",
        )

    def test_minimal_manifest_is_safe_and_returns_an_inventory(self) -> None:
        manifest = _minimal_safe_manifest()
        inventory = validate_chrome_permissions(manifest)

        self.assertEqual(inventory.manifest_version, 3)
        self.assertEqual(
            inventory.all_host_patterns,
            ALLOWED_CHROME_HOST_PATTERNS | ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
        )
        self.assertEqual(inventory.api_permissions, ("sidePanel",))
        self.assertTrue(is_chrome_permission_set_safe(manifest))

    def test_exact_static_content_script_surface_is_admitted(self) -> None:
        manifest = _minimal_safe_manifest()
        inventory = validate_chrome_permissions(manifest)
        self.assertEqual(
            inventory.all_host_patterns,
            ALLOWED_CHROME_HOST_PATTERNS | ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
        )
        self.assertEqual(len(inventory.match_surfaces), 1)

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

    def test_optional_loopback_host_or_api_permissions_are_still_rejected(self) -> None:
        for key, value in (
            ("optional_host_permissions", ["http://localhost/*"]),
            ("optional_permissions", ["sidePanel"]),
        ):
            manifest = _minimal_safe_manifest()
            manifest[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)

    def test_privileged_write_and_generic_api_permissions_are_rejected(self) -> None:
        capabilities = FORBIDDEN_CHROME_API_PERMISSIONS
        for surface in ("permissions", "optional_permissions"):
            for capability in capabilities:
                manifest = _minimal_safe_manifest()
                manifest[surface] = [capability]
                with self.subTest(surface=surface, capability=capability):
                    with self.assertRaises(ChromePermissionViolation) as caught:
                        validate_chrome_permissions(manifest)
                    self.assertNotIn(capability, str(caught.exception))

    def test_side_panel_is_required_and_is_the_only_api_permission(self) -> None:
        for permissions in (
            [],
            ["sidePanel", "storage"],
            ["sidePanel", "sidePanel"],
            ["sidePanel", "futureDangerousCapability"],
        ):
            manifest = _minimal_safe_manifest()
            manifest["permissions"] = permissions
            with self.subTest(permissions=permissions):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)

    def test_nonlocal_content_script_match_or_exclusion_is_rejected(self) -> None:
        canary = _match_pattern("https", _outside_host())
        for key in ("matches", "exclude_matches"):
            manifest = _minimal_safe_manifest()
            script: dict[str, object] = {
                "matches": sorted(ALLOWED_CHROME_CONTENT_MATCH_PATTERNS),
                "js": ["reader.js"],
            }
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
            script: dict[str, object] = {
                "matches": sorted(ALLOWED_CHROME_CONTENT_MATCH_PATTERNS),
                "js": ["reader.js"],
            }
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

    def test_local_resource_paths_and_extension_csp_fail_closed(self) -> None:
        mutations = (
            ("background", {"service_worker": "../worker.js"}),
            (
                "background",
                {"service_worker": "https:" + "//" + _outside_host() + "/worker.js"},
            ),
            ("side_panel", {"default_path": "/panel.html"}),
            ("side_panel", {"default_path": "side_panel/index.html?mode=unsafe"}),
            ("content_security_policy", {"extension_pages": "script-src 'unsafe-inline'"}),
            (
                "content_security_policy",
                {"extension_pages": EXTENSION_PAGE_CSP, "sandbox": "allow-scripts"},
            ),
        )
        for key, value in mutations:
            manifest = _minimal_safe_manifest()
            manifest[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ChromePermissionViolation):
                    validate_chrome_permissions(manifest)

    def test_content_script_resources_are_local_idle_and_script_only(self) -> None:
        unsafe_scripts = (
            {
                "matches": list(ALLOWED_CHROME_CONTENT_MATCH_PATTERNS),
                "js": ["../reader.js"],
            },
            {
                "matches": list(ALLOWED_CHROME_CONTENT_MATCH_PATTERNS),
                "js": ["reader.html"],
            },
            {
                "matches": list(ALLOWED_CHROME_CONTENT_MATCH_PATTERNS),
                "js": ["reader.js"],
                "run_at": "document_start",
            },
            {
                "matches": list(ALLOWED_CHROME_CONTENT_MATCH_PATTERNS),
                "js": ["reader.js"],
                "css": ["mutation.css"],
            },
        )
        for script in unsafe_scripts:
            manifest = _minimal_safe_manifest()
            manifest["content_scripts"] = [script]
            with self.subTest(script=script):
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
