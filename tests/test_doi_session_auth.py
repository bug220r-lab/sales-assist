"""Synthetic source-schema, renewal and no-repeat-write acceptance checks."""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from doi_draft_transfer import local_auth, session_auth as auth
from doi_draft_transfer.contract import MAILBOX_ID, USER_ID, TransferError
from doi_draft_transfer.helpscout import HelpScoutDraftClient
from tests.test_doi_draft_transfer import synthetic_row

SYN_PATH = r"C:\SYNTHETIC-ONLY\session-connection.dpapi"
OLD = "SYN-OLD-DUMMY-TOKEN"
NEW = "SYN-NEW-DUMMY-TOKEN"


def record(**changes):
    return {"client_id": "SYN-APP-ID", "client_secret": "SYN-APP-SECRET",
            "access_token": OLD, "expires_at": 1000, "user_id": str(USER_ID)} | changes


def response(status=200, value=None, raw=None, headers=()):
    value = value if value is not None else {
        "token_type": "bearer", "access_token": NEW, "expires_in": 172800
    }
    result = Mock(status=status)
    result.read.return_value = raw if raw is not None else json.dumps(value).encode()
    result.getheaders.return_value = headers
    return result


class SessionFixture(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.value = record()
        self.plains = []
        self.calls, self.token_responses, self.api_responses = [], [], []
        self.read = self.enterContext(patch.object(
            local_auth, "_read_encrypted", return_value=b"SYN"
        ))
        self.decode = self.enterContext(patch.object(
            local_auth, "_unprotect", side_effect=self.plain
        ))
        self.lease = self.enterContext(patch.object(auth, "SessionLease"))
        self.http = self.enterContext(patch.object(auth.http.client, "HTTPSConnection",
                                                 side_effect=self.connection))
        self.provider = self.make_provider()
        self.client = HelpScoutDraftClient(token_provider=self.provider)

    def plain(self, raw):
        result = bytearray(json.dumps(self.value).encode())
        self.plains.append(result)
        return result

    def make_provider(self):
        provider = auth.SessionClientCredentials(
            SYN_PATH, ownership="cleanup-complete", clock=lambda: self.now
        )
        self.addCleanup(provider.close)
        return provider

    def connection(self, host, **kwargs):
        self.assertEqual(host, auth.HOST)
        self.assertEqual(kwargs["timeout"], 15)
        connection = Mock()
        last = []

        def request(method, path, **options):
            last[:] = [method, path]
            self.calls.append((method, path, options))

        def getresponse():
            queue = self.token_responses if last[1] == auth.TOKEN_PATH else self.api_responses
            result = queue.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        connection.request.side_effect = request
        connection.getresponse.side_effect = getresponse
        return connection

    def token_calls(self):
        return [call for call in self.calls if call[1] == auth.TOKEN_PATH]


class SessionProviderTests(SessionFixture):
    def test_explicit_mode_and_ownership_are_lazy_and_ambiguous_settings_stop(self):
        env = {"SSA_HELPSCOUT_AUTH_MODE": auth.MODE, "SSA_HELPSCOUT_DPAPI_AUTH_PATH": SYN_PATH,
               "SSA_HELPSCOUT_SESSION_RENEWAL": "1",
               "SSA_HELPSCOUT_RENEWAL_OWNERSHIP": "cleanup-complete"}
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(HelpScoutDraftClient.from_environment())
        env["SSA_HELPSCOUT_DRAFT_TRANSFER"] = "1"
        with patch.dict(os.environ, env, clear=True):
            client = HelpScoutDraftClient.from_environment()
            self.assertIsInstance(client._token_provider, auth.SessionClientCredentials)
            client.close()
        for change in (
            {"SSA_HELPSCOUT_SESSION_RENEWAL": "0"},
            {"SSA_HELPSCOUT_RENEWAL_OWNERSHIP": "cleanup-running"},
            {"SSA_HELPSCOUT_ACCESS_TOKEN": OLD},
            {"SSA_HELPSCOUT_AUTH_MODE": "dpapi-cached-token"},
        ):
            with patch.dict(os.environ, env | change, clear=True), self.assertRaises(TransferError):
                HelpScoutDraftClient.from_environment()
        self.read.assert_not_called()
        self.decode.assert_not_called()
        self.http.assert_not_called()
        self.lease.return_value.acquire.assert_not_called()

    def test_source_legacy_schema_loads_once_and_clears_plaintext(self):
        self.assertEqual(self.provider(), OLD)
        self.assertEqual(self.provider(), OLD)
        self.read.assert_called_once_with(SYN_PATH)
        self.decode.assert_called_once()
        self.assertTrue(all(set(value) == {0} for value in self.plains))
        self.assertNotIn(OLD, repr(self.provider))
        self.assertNotIn(SYN_PATH, repr(self.provider))
        self.http.assert_not_called()

    def test_conflicting_or_unknown_grant_schema_never_renews(self):
        for extra in ({"refresh_token": "SYN-REFRESH"}, {"grant_type": "refresh_token"},
                      {"grant_type": "authorization_code"}, {"unknown": "SYN"}):
            self.value = record(**extra)
            with self.assertRaisesRegex(TransferError, "GRANT_AMBIGUOUS"):
                self.make_provider()()
        self.http.assert_not_called()

    def test_invalid_identity_record_or_duplicate_key_is_terminal_and_redacted(self):
        for changes in ({"user_id": True}, {"user_id": "SYN-WRONG"},
                        {"expires_at": float("nan")}, {"expires_at": "1000"},
                        {"client_secret": "SYN\r\nSECRET"}, {"token_type": 1}):
            self.value = record(**changes)
            provider = self.make_provider()
            for _ in range(2):
                with self.assertRaises(TransferError) as caught:
                    provider()
                self.assertNotIn("SYN", str(caught.exception))
        self.decode.side_effect = lambda _: bytearray(b'{"client_id":"SYN-A","client_id":"SYN-B"}')
        with self.assertRaises(TransferError):
            self.make_provider()()
        self.http.assert_not_called()

    def test_owner_conflict_and_access_denial_precede_network_and_never_reload(self):
        self.lease.return_value.acquire.side_effect = TransferError(
            "HELP_SCOUT_RENEWAL_OWNER_CONFLICT", 503
        )
        with self.assertRaisesRegex(TransferError, "OWNER_CONFLICT"):
            self.provider()
        self.read.assert_not_called()
        self.lease.return_value.acquire.side_effect = None
        self.read.side_effect = PermissionError("SYN private detail")
        provider = self.make_provider()
        for _ in range(2):
            with self.assertRaisesRegex(TransferError, "ACCESS_DENIED"):
                provider()
        self.read.assert_called_once()
        self.http.assert_not_called()

    def test_margin_is_a_hold_then_actual_expiry_allows_one_memory_only_renewal(self):
        self.now = 880
        with self.assertRaisesRegex(TransferError, "MARGIN_HOLD"):
            self.provider()
        self.http.assert_not_called()
        self.now = 1000
        self.token_responses = [response()]
        with patch.object(Path, "write_bytes", side_effect=AssertionError("No writes")), \
                patch.object(Path, "write_text", side_effect=AssertionError("No writes")):
            self.assertEqual(self.provider(), NEW)
        call = self.token_calls()[0]
        self.assertEqual(call[:2], ("POST", "/v2/oauth2/token"))
        self.assertEqual(parse_qs(call[2]["body"].decode()), {
            "grant_type": ["client_credentials"], "client_id": ["SYN-APP-ID"],
            "client_secret": ["SYN-APP-SECRET"],
        })
        self.assertNotIn("Authorization", call[2]["headers"])
        self.assertIsNone(self.provider._client_secret)
        self.assertEqual(self.provider(), NEW)
        self.assertEqual(len(self.token_calls()), 1)

    def test_concurrent_expiry_uses_one_read_and_one_reserved_issuance(self):
        self.now = 1000
        self.token_responses = [response()]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(lambda _: self.provider(), range(16))), [NEW] * 16)
        self.read.assert_called_once()
        self.assertEqual(len(self.token_calls()), 1)

    def test_stale_401_does_not_reject_new_generation_or_issue_twice(self):
        self.assertEqual(self.provider(), OLD)
        self.provider.note_unauthorized(OLD)
        self.token_responses = [response()]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(lambda _: self.provider(), range(16))), [NEW] * 16)
        self.provider.note_unauthorized(OLD)
        self.assertEqual(self.provider(), NEW)
        self.assertEqual(len(self.token_calls()), 1)

    def test_denial_redirect_rate_limit_and_uncertain_renewal_are_terminal(self):
        self.now = 1000
        cases = [response(status=status) for status in (301, 401, 403, 429, 500)]
        cases += [TimeoutError("SYN secret detail"), OSError("SYN secret detail")]
        for result in cases:
            provider = self.make_provider()
            self.token_responses = [result]
            before = len(self.token_calls())
            for _ in range(2):
                with self.assertRaisesRegex(TransferError, "RENEWAL_STOPPED") as caught:
                    provider()
                self.assertNotIn("SYN", str(caught.exception))
            self.assertEqual(len(self.token_calls()), before + 1)

    def test_malformed_bounded_or_unchanged_token_response_stops(self):
        self.now = 1000
        base = {"token_type": "bearer", "access_token": NEW, "expires_in": 172800}
        cases = [response(value=base | change) for change in (
            {"expires_in": True}, {"expires_in": "172800"}, {"expires_in": 120},
            {"expires_in": 172801}, {"access_token": OLD}, {"token_type": "other"},
            {"refresh_token": "SYN-UNEXPECTED"},
        )]
        cases += [response(raw=b"x" * (auth.MAX_TOKEN_RESPONSE + 1)),
                  response(raw=b'{"access_token":"SYN-A","access_token":"SYN-B"}')]
        for result in cases:
            self.token_responses = [result]
            with self.assertRaisesRegex(TransferError, "RENEWAL_STOPPED"):
                self.make_provider()()

    def test_renewed_token_rejection_later_expiry_and_close_cannot_issue_again(self):
        self.now = 1000
        self.token_responses = [response()]
        self.assertEqual(self.provider(), NEW)
        self.provider.note_unauthorized(NEW)
        with self.assertRaisesRegex(TransferError, "RENEWED_TOKEN_REJECTED"):
            self.provider()
        other = self.make_provider()
        self.token_responses = [response()]
        other()
        self.now = 200000
        with self.assertRaisesRegex(TransferError, "RENEWAL_LIMIT"):
            other()
        other.close()
        with self.assertRaisesRegex(TransferError, "AUTH_CLOSED"):
            other()
        self.assertEqual(len(self.token_calls()), 2)
        self.assertIsNone(other._token)
        self.assertIsNone(other._client_secret)


class SessionHTTPTests(SessionFixture):
    def test_destination_get_401_renews_once_and_retries_only_that_read(self):
        self.token_responses = [response()]
        self.api_responses = [response(401), response(value={"id": MAILBOX_ID}),
                              response(value={"id": USER_ID})]
        self.assertTrue(self.client.check_destination()["verified"])
        self.assertEqual([item[:2] for item in self.calls], [
            ("GET", f"/v2/mailboxes/{MAILBOX_ID}"), ("POST", auth.TOKEN_PATH),
            ("GET", f"/v2/mailboxes/{MAILBOX_ID}"), ("GET", f"/v2/users/{USER_ID}"),
        ])

    def test_draft_post_401_never_renews_or_replays_until_explicit_next_action(self):
        self.api_responses = [response(401)]
        result = self.client.create_draft(synthetic_row())
        self.assertEqual(result["state"], "AUTH_REQUIRED")
        self.assertEqual([item[:2] for item in self.calls], [("POST", "/v2/conversations")])
        self.token_responses = [response()]
        self.api_responses = [response(value={"id": MAILBOX_ID}), response(value={"id": USER_ID})]
        self.assertTrue(self.client.check_destination()["verified"])
        self.assertEqual(sum(path == "/v2/conversations" for _, path, _ in self.calls), 1)

    def test_second_401_and_429_never_start_another_renewal(self):
        self.token_responses = [response()]
        self.api_responses = [response(401), response(401)]
        with self.assertRaises(TransferError):
            self.client.check_destination()
        count = len(self.calls)
        with self.assertRaisesRegex(TransferError, "RENEWED_TOKEN_REJECTED"):
            self.client.check_destination()
        self.assertEqual(len(self.calls), count)
        other = HelpScoutDraftClient(token_provider=self.make_provider())
        self.api_responses = [response(429)]
        with self.assertRaises(TransferError):
            other.check_destination()
        self.assertEqual(len(self.token_calls()), 1)

    def test_known_draft_id_survives_readback_renewal_failure_without_repeat_create(self):
        self.token_responses = [response(403)]
        self.api_responses = [response(201, headers=[("Resource-ID", "99000001")]), response(401)]
        result = self.client.create_draft(synthetic_row())
        self.assertEqual(result["state"], "CREATED_UNVERIFIED")
        self.assertEqual(result["conversation_id"], "99000001")
        self.assertFalse(result["retry_allowed"])
        self.client.verify_draft(synthetic_row(), result)
        self.assertEqual(sum(path == "/v2/conversations" for _, path, _ in self.calls), 1)

    def test_uncertain_post_does_not_trigger_renewal_or_retry(self):
        self.api_responses = [TimeoutError("SYN uncertain create")]
        result = self.client.create_draft(synthetic_row())
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.token_calls(), [])


@unittest.skipUnless(os.name == "nt", "Windows named session lease")
class SessionLeaseTests(unittest.TestCase):
    def test_fixed_scope_lease_rejects_second_owner_and_closes_across_threads(self):
        name = "Global\\SalesAssist.SYNTHETIC." + uuid.uuid4().hex
        first, second = auth.SessionLease(), auth.SessionLease()
        self.assertEqual(first._name, second._name)
        first._name = second._name = name
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        first.acquire()
        with self.assertRaisesRegex(TransferError, "OWNER_CONFLICT"):
            second.acquire()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pool.submit(first.close).result()
        second.acquire()

    def test_second_process_is_excluded_and_process_death_releases_lease(self):
        name = "Global\\SalesAssist.SYNTHETIC." + uuid.uuid4().hex
        source = str(Path(auth.__file__).resolve().parents[1])
        code = (
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "from doi_draft_transfer.session_auth import SessionLease; "
            "lease=SessionLease(); lease._name=sys.argv[2]; lease.acquire(); "
            "print('SYN-LEASE-READY',flush=True); sys.stdin.readline()"
        )
        process = subprocess.Popen([sys.executable, "-B", "-I", "-c", code, source, name],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        try:
            self.assertEqual(process.stdout.readline().strip(), "SYN-LEASE-READY")
            lease = auth.SessionLease()
            lease._name = name
            self.addCleanup(lease.close)
            with self.assertRaisesRegex(TransferError, "OWNER_CONFLICT"):
                lease.acquire()
            process.kill()
            process.communicate(timeout=10)
            lease.acquire()
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
