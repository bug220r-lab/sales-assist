"""Synthetic authentication fixtures only; no real DPAPI connection or live HTTP."""

from __future__ import annotations

import concurrent.futures
import ctypes
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from doi_draft_transfer import local_auth as auth
from doi_draft_transfer.contract import MAILBOX_ID, USER_ID, TransferError
from doi_draft_transfer.helpscout import HelpScoutDraftClient
from tests.test_doi_draft_transfer import synthetic_row

SYN_PATH = r"C:\SYNTHETIC-ONLY\connection.dpapi"
SYN_TOKEN = "SYN-DUMMY-NOT-A-CREDENTIAL"


def record(**changes):
    values = {"access_token": SYN_TOKEN, "expires_at": 1000, "client_secret": "SYN-UNUSED"}
    values.update(changes)
    return bytearray(json.dumps(values).encode())


class CachedTokenTests(unittest.TestCase):
    def setUp(self):
        self.read = patch.object(auth, "_read_encrypted", return_value=b"SYN-CIPHERTEXT")
        self.decode = patch.object(auth, "_unprotect", side_effect=lambda raw: record())
        self.read_mock, self.decode_mock = self.read.start(), self.decode.start()
        self.addCleanup(self.read.stop)
        self.addCleanup(self.decode.stop)
        self.now = 100
        self.provider = auth.CachedDPAPIToken(SYN_PATH, clock=lambda: self.now)

    def test_lazy_construction_and_concurrent_calls_load_once_without_retaining_record(self):
        self.read_mock.assert_not_called()
        self.decode_mock.assert_not_called()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(lambda _: self.provider(), range(16))), [SYN_TOKEN] * 16)
        self.read_mock.assert_called_once_with(SYN_PATH)
        self.decode_mock.assert_called_once_with(b"SYN-CIPHERTEXT")
        self.assertNotIn("_auth", vars(self.provider))
        self.assertNotIn("SYN-UNUSED", str(vars(self.provider)))
        self.assertNotIn(SYN_TOKEN, repr(self.provider))
        self.assertNotIn(SYN_PATH, repr(self.provider))

    def test_expiry_margin_and_later_expiry_are_terminal_without_reload(self):
        self.assertEqual(self.provider(), SYN_TOKEN)
        self.now = 879
        self.assertEqual(self.provider(), SYN_TOKEN)
        self.now = 880
        for _ in range(2):
            with self.assertRaisesRegex(TransferError, "CACHED_TOKEN_EXPIRED"):
                self.provider()
        self.assertIsNone(self.provider._token)
        self.read_mock.assert_called_once()
        self.decode_mock.assert_called_once()

    def test_initial_expiry_and_bad_records_fail_closed_and_clear_plaintext(self):
        cases = [
            record(expires_at=220), record(expires_at=True), record(expires_at="1000"),
            record(expires_at=float("nan")), record(expires_at=float("inf")),
            record(access_token=""), record(access_token="SYN\r\nDUMMY"),
            record(access_token="SYN-\u00e9"), record(token_type="other"),
            bytearray(b'[]'), bytearray(b'not JSON'),
            bytearray(b'{"access_token":"SYN-A","access_token":"SYN-B","expires_at":1000}'),
            bytearray(b"x" * (auth.MAX_CONNECTION_BYTES + 1)),
        ]
        for plain in cases:
            with self.subTest(size=len(plain)):
                self.decode_mock.side_effect = None
                self.decode_mock.return_value = plain
                provider = auth.CachedDPAPIToken(SYN_PATH, clock=lambda: 100)
                with self.assertRaises(TransferError) as caught:
                    provider()
                self.assertIn(caught.exception.code, {
                    "HELP_SCOUT_CACHED_TOKEN_EXPIRED", "HELP_SCOUT_LOCAL_AUTH_REQUIRED"
                })
                self.assertEqual(set(plain), {0})
                self.assertIsNone(provider._token)

    def test_permission_denial_and_decoder_failure_never_echo_or_retry(self):
        for failure, code in [
            (PermissionError("SYN private path and credential"), "CONNECTION_ACCESS_DENIED"),
            (OSError("SYN private path and credential"), "LOCAL_AUTH_REQUIRED"),
        ]:
            self.read_mock.side_effect = failure
            provider = auth.CachedDPAPIToken(SYN_PATH, clock=lambda: 100)
            start = self.read_mock.call_count
            for _ in range(2):
                with self.assertRaisesRegex(TransferError, code) as caught:
                    provider()
                self.assertNotIn("SYN", str(caught.exception))
            self.assertEqual(self.read_mock.call_count, start + 1)
        self.decode_mock.assert_not_called()
        self.read_mock.side_effect = None
        self.decode_mock.side_effect = RuntimeError("SYN private decoder detail")
        with self.assertRaisesRegex(TransferError, "LOCAL_AUTH_REQUIRED"):
            self.provider()

    def test_ciphertext_bound_precedes_decoder(self):
        for raw in (b"", b"x" * (auth.MAX_CONNECTION_BYTES + 1)):
            self.read_mock.return_value = raw
            with self.assertRaisesRegex(TransferError, "LOCAL_AUTH_REQUIRED"):
                auth.CachedDPAPIToken(SYN_PATH)()
        self.decode_mock.assert_not_called()

    def test_off_mode_and_ambiguous_configuration_never_load_credentials(self):
        env = {"SSA_HELPSCOUT_AUTH_MODE": "dpapi-cached-token",
               "SSA_HELPSCOUT_DPAPI_AUTH_PATH": SYN_PATH}
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(HelpScoutDraftClient.from_environment())
        env["SSA_HELPSCOUT_DRAFT_TRANSFER"] = "1"
        with patch.dict(os.environ, env, clear=True):
            client = HelpScoutDraftClient.from_environment()
            self.assertIsInstance(client._token_provider, auth.CachedDPAPIToken)
        for change in [
            {"SSA_HELPSCOUT_ACCESS_TOKEN": SYN_TOKEN},
            {"SSA_HELPSCOUT_AUTH_MODE": "unknown"},
            {"SSA_HELPSCOUT_AUTH_MODE": "access-token"},
            {"SSA_HELPSCOUT_DPAPI_AUTH_PATH": ""},
        ]:
            with patch.dict(os.environ, env | change, clear=True):
                with self.assertRaises(TransferError):
                    HelpScoutDraftClient.from_environment()
        self.read_mock.assert_not_called()
        self.decode_mock.assert_not_called()

    def test_legacy_token_injection_stays_compatible(self):
        with patch.dict(os.environ, {
            "SSA_HELPSCOUT_DRAFT_TRANSFER": "1", "SSA_HELPSCOUT_ACCESS_TOKEN": SYN_TOKEN
        }, clear=True):
            client = HelpScoutDraftClient.from_environment()
        self.assertEqual(client._token, SYN_TOKEN)
        self.assertIsNone(client._token_provider)
        self.read_mock.assert_not_called()

    def test_read_only_access_check_uses_fixed_endpoints_and_no_renewal_on_401(self):
        client = HelpScoutDraftClient(token_provider=self.provider)
        connection = Mock()
        first, second = Mock(status=200), Mock(status=200)
        first.read.return_value = json.dumps({"id": MAILBOX_ID}).encode()
        second.read.return_value = json.dumps({"id": USER_ID}).encode()
        first.getheaders.return_value = second.getheaders.return_value = []
        connection.getresponse.side_effect = [first, second]
        with patch("doi_draft_transfer.helpscout.http.client.HTTPSConnection",
                   return_value=connection):
            self.assertTrue(client.check_destination()["verified"])
            self.assertEqual([call.args[:2] for call in connection.request.call_args_list], [
                ("GET", f"/v2/mailboxes/{MAILBOX_ID}"), ("GET", f"/v2/users/{USER_ID}")
            ])
            for call in connection.request.call_args_list:
                self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer " + SYN_TOKEN)
            connection.reset_mock()
            first.status = 401
            connection.getresponse.side_effect = [first]
            with self.assertRaisesRegex(TransferError, "AUTH_EXPIRED"):
                client.check_destination()
            self.assertEqual(connection.request.call_count, 1)
        self.read_mock.assert_called_once()
        self.decode_mock.assert_called_once()

    def test_local_auth_failure_never_opens_http_or_becomes_unknown_write(self):
        self.now = 1000
        client = HelpScoutDraftClient(token_provider=self.provider)
        with patch("doi_draft_transfer.helpscout.http.client.HTTPSConnection") as connection:
            result = client.create_draft(synthetic_row())
            self.assertEqual(result, {"state": "AUTH_REQUIRED",
                             "code": "HELP_SCOUT_CACHED_TOKEN_EXPIRED", "retry_allowed": True})
            previous = {"conversation_id": "99000001", "state": "CREATED",
                        "operation_id": "SYN-OPERATION", "retry_allowed": False}
            current = client.verify_draft(synthetic_row(), previous)
            self.assertEqual(current["state"], "CREATED_UNVERIFIED")
            self.assertEqual(current["conversation_id"], previous["conversation_id"])
            self.assertFalse(current["retry_allowed"])
            with self.assertRaisesRegex(TransferError, "CACHED_TOKEN_EXPIRED"):
                client.check_destination()
            connection.assert_not_called()

    def test_expiry_after_create_preserves_known_id_without_second_http_request(self):
        token = Mock(side_effect=[SYN_TOKEN, TransferError("HELP_SCOUT_CACHED_TOKEN_EXPIRED", 503)])
        client = HelpScoutDraftClient(token_provider=token)
        response = Mock(status=201)
        response.read.return_value = b""
        response.getheaders.return_value = [("Resource-ID", "99000001")]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("doi_draft_transfer.helpscout.http.client.HTTPSConnection",
                   return_value=connection) as factory:
            result = client.create_draft(synthetic_row())
        self.assertEqual(result["state"], "CREATED_UNVERIFIED")
        self.assertEqual(result["conversation_id"], "99000001")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(connection.request.call_args.args[:2], ("POST", "/v2/conversations"))


class WindowsBoundaryTests(unittest.TestCase):
    def test_unsafe_path_spellings_are_rejected_without_filesystem_access(self):
        for path in [None, "", "connection.dpapi", r"C:connection.dpapi",
                     r"\\server\share\connection.dpapi", r"\\?\C:\connection.dpapi",
                     r"C:\folder\..\connection.dpapi", r"C:\folder\connection.dpapi:stream",
                     r"C:\folder.\connection.dpapi", r"C:\folder\connection.json"]:
            with self.subTest(path=path), self.assertRaises(TransferError):
                auth.CachedDPAPIToken(path)
        self.assertEqual(auth.connection_path(SYN_PATH), SYN_PATH)

    def test_non_windows_fails_without_loading_native_library(self):
        with patch.object(auth.os, "name", "posix"), patch.object(auth, "_dll") as dll:
            for call in (lambda: auth._read_encrypted(SYN_PATH), lambda: auth._unprotect(b"SYN")):
                with self.assertRaisesRegex(TransferError, "DPAPI_UNAVAILABLE"):
                    call()
            dll.assert_not_called()

    def test_fixed_drive_and_reparse_checks_precede_file_open(self):
        info = SimpleNamespace(st_file_attributes=0, st_mode=0o100600)
        ancestor = Mock()
        ancestor.lstat.return_value = info
        leaf = Mock(anchor="C:\\", parents=[ancestor])
        leaf.lstat.return_value = info
        kernel = Mock()
        with patch.object(auth, "_dll", return_value=kernel):
            kernel.GetDriveTypeW.return_value = 4
            with self.assertRaises(ValueError):
                auth._local_regular_path(leaf)
            leaf.lstat.assert_not_called()
            kernel.GetDriveTypeW.return_value = 3
            ancestor.lstat.return_value = SimpleNamespace(st_file_attributes=0x400)
            with self.assertRaises(ValueError):
                auth._local_regular_path(leaf)
            leaf.lstat.assert_not_called()
            ancestor.lstat.return_value = info
            self.assertIs(auth._local_regular_path(leaf), info)

    @unittest.skipUnless(os.name == "nt", "Windows regular-file metadata")
    def test_synthetic_encrypted_file_is_read_only_and_changed_file_rejected(self):
        with tempfile.TemporaryDirectory(
            prefix="ssa-synthetic-dpapi-", dir=os.environ.get("SSA_TRANSFER_TEST_ROOT")
        ) as folder:
            path = Path(folder) / "connection.dpapi"
            path.write_bytes(b"SYN-CIPHERTEXT")
            before = path.stat()
            kernel = Mock()
            kernel.GetDriveTypeW.return_value = 3
            with patch.object(auth, "_dll", return_value=kernel):
                self.assertEqual(auth._read_encrypted(str(path)), b"SYN-CIPHERTEXT")
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
            changed = SimpleNamespace(st_dev=before.st_dev, st_ino=before.st_ino,
                                      st_size=before.st_size, st_mtime_ns=before.st_mtime_ns + 1)
            with patch.object(auth, "_local_regular_path", side_effect=[before, changed]):
                with self.assertRaises(ValueError):
                    auth._read_encrypted(str(path))

    def test_mocked_dpapi_uses_no_ui_frees_and_clears_native_output(self):
        native = ctypes.create_string_buffer(b"SYN-PLAINTEXT")
        crypt, kernel = Mock(), Mock()
        def decrypt(source, description, entropy, reserved, prompt, flags, result):
            self.assertIsNone(description)
            self.assertIsNone(entropy)
            self.assertIsNone(reserved)
            self.assertIsNone(prompt)
            self.assertEqual(flags, 1)
            output = ctypes.cast(result, ctypes.POINTER(auth._Blob)).contents
            output.size = len(b"SYN-PLAINTEXT")
            output.data = ctypes.cast(native, ctypes.POINTER(ctypes.c_ubyte))
            return True
        crypt.CryptUnprotectData.side_effect = decrypt
        with patch.object(auth.os, "name", "nt"), patch.object(auth, "_dll",
                side_effect=lambda name: crypt if name == "crypt32.dll" else kernel):
            self.assertEqual(auth._unprotect(b"SYN-CIPHERTEXT"), b"SYN-PLAINTEXT")
        kernel.LocalFree.assert_called_once()
        self.assertEqual(native.raw, b"\0" * len(native.raw))


if __name__ == "__main__":
    unittest.main()
