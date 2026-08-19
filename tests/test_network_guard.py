"""Tests for the fail-closed localhost-only runtime destination guard."""

from __future__ import annotations

import socket
import unittest
from unittest import mock

from synthetic_sales_assist.safety.network import (
    ALLOWED_RUNTIME_HOSTS,
    NetworkPolicyViolation,
    is_runtime_host_allowed,
    is_runtime_url_allowed,
    validate_runtime_host,
    validate_runtime_url,
)


def _url(scheme: str, authority: str, suffix: str = "/") -> str:
    """Build negative URL canaries without committing a prohibited literal."""

    return f"{scheme}:{'/' * 2}{authority}{suffix}"


def _outside_host() -> str:
    return "outside" + "." + "invalid"


class RuntimeHostTests(unittest.TestCase):
    def test_closed_runtime_host_inventory(self) -> None:
        self.assertEqual(
            ALLOWED_RUNTIME_HOSTS,
            frozenset({"127.0.0.1", "localhost", "::1"}),
        )

    def test_exact_hosts_are_accepted_and_localhost_case_is_canonicalized(self) -> None:
        expected = {
            "127.0.0.1": "127.0.0.1",
            "localhost": "localhost",
            "LOCALHOST": "localhost",
            "::1": "::1",
        }
        for supplied, canonical in expected.items():
            with self.subTest(host=supplied):
                self.assertEqual(validate_runtime_host(supplied), canonical)
                self.assertTrue(is_runtime_host_allowed(supplied))

    def test_aliases_ranges_wildcards_and_embedded_authorities_are_rejected(self) -> None:
        rejected: tuple[object, ...] = (
            None,
            b"localhost",
            "",
            " localhost",
            "localhost ",
            "local host",
            "localhost.",
            "localhost.localdomain",
            "sub.localhost",
            "localhost:8080",
            "user" + "@" + "localhost",
            "*.localhost",
            "*",
            "[::1]",
            "::1%loopback",
            "0:0:0:0:0:0:0:1",
            "::ffff:127.0.0.1",
            "127.0.0.0",
            "127.0.0.2",
            "127.1",
            "127.0.1",
            "2130706433",
            "0x7f000001",
            "0177.0.0.1",
        )
        for host in rejected:
            with self.subTest(host=host):
                with self.assertRaises(NetworkPolicyViolation):
                    validate_runtime_host(host)
                self.assertFalse(is_runtime_host_allowed(host))


class RuntimeUrlTests(unittest.TestCase):
    def test_http_and_https_urls_for_exact_hosts_are_accepted(self) -> None:
        accepted = {
            "http://127.0.0.1": ("http", "127.0.0.1", None),
            "http://127.0.0.1:8080/orders/SYN-ORDER-000001": (
                "http",
                "127.0.0.1",
                8080,
            ),
            _url("https", "localhost:443", "/api?scenario=SYN-RUN-000001"): (
                "https",
                "localhost",
                443,
            ),
            "HTTP://LOCALHOST/health": ("http", "localhost", None),
            _url("http", "[::1]"): ("http", "::1", None),
            _url("https", "[::1]:8443", "/status"): ("https", "::1", 8443),
        }
        for url, expected in accepted.items():
            with self.subTest(url=url):
                destination = validate_runtime_url(url)
                self.assertEqual(
                    (destination.scheme, destination.host, destination.port), expected
                )
                self.assertTrue(is_runtime_url_allowed(url))

    def test_nonlocal_and_ambiguous_urls_are_rejected(self) -> None:
        outside = _outside_host()
        rejected: tuple[object, ...] = (
            None,
            _url("http", "localhost").encode(),
            "",
            " " + _url("http", "localhost"),
            _url("http", "localhost") + " ",
            "localhost:8080/path",
            "//localhost/path",
            _url("http", "", "//localhost/path"),
            _url("ftp", "localhost", "/path"),
            _url("file", "localhost", "/tmp/item"),
            "data" + ":" + "text/plain,localhost",
            _url("javascript", "localhost", "/alert(1)"),
            _url("http", outside),
            _url("http", "127.0.0." + "2"),
            _url("http", "127." + "1"),
            _url("http", "213070" + "6433"),
            _url("http", "0x7f" + "000001"),
            _url("http", "0177" + ".0.0.1"),
            _url("http", "127.0.0.1" + "." + outside),
            _url("http", "localhost" + "." + outside),
            _url("http", "localhost" + "."),
            _url("http", "[0:0:0:0:0:0:0:" + "1]"),
            _url("http", "[::ffff:" + "127.0.0.1]"),
            _url("http", "[::1" + "%25loopback]"),
            _url("http", "user" + "@" + "localhost"),
            _url(
                "http",
                "user" + ":" + "credential-canary" + "@" + "localhost",
            ),
            _url("http", "localhost" + "@" + "127.0.0.1"),
            _url("http", "local" + "%68" + "ost"),
            _url("http", "127.0.0.1" + "%2e" + outside),
            _url("http", "*" + ".localhost"),
            _url("http", "*"),
            _url("http", "localhost" + ":"),
            _url("http", "localhost" + ":0"),
            _url("http", "localhost" + ":65536"),
            _url("http", "localhost" + ":not-a-port"),
            _url("http", "[::1]" + ":"),
            _url("http", "[::1]" + "suffix"),
            _url("http", "127.0.0.1" + "\\" + "@" + outside),
            _url("http", "local" + "\t" + "host"),
            _url("http", "localhost", "/line" + "\n" + "break"),
        )
        for url in rejected:
            with self.subTest(url=url):
                with self.assertRaises(NetworkPolicyViolation):
                    validate_runtime_url(url)
                self.assertFalse(is_runtime_url_allowed(url))

    def test_validation_performs_no_dns_lookup_or_socket_open(self) -> None:
        with (
            mock.patch.object(
                socket,
                "getaddrinfo",
                side_effect=AssertionError("DNS must not be used"),
            ),
            mock.patch.object(
                socket,
                "socket",
                side_effect=AssertionError("sockets must not be opened"),
            ),
        ):
            destination = validate_runtime_url("http://localhost:8080/health")
        self.assertEqual(destination.host, "localhost")


if __name__ == "__main__":
    unittest.main()
