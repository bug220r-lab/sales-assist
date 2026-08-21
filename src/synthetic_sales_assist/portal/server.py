"""Bounded single-threaded localhost HTTP service for the synthetic portal."""

from __future__ import annotations

import hmac
import os
import re
import socket
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Final, cast

from synthetic_sales_assist.persistence.paths import DataPaths, resolve_data_paths
from synthetic_sales_assist.portal.assets import STATIC_ASSETS
from synthetic_sales_assist.portal.contracts import (
    MAX_REQUEST_BODY_BYTES,
    MAX_RESPONSE_BODY_BYTES,
    PortalContractError,
    ScenarioApplicationProtocol,
    error_bytes,
    parse_evaluate_request,
    parse_instantiate_request,
    parse_shutdown_request,
    response_bytes,
    validate_alias,
    validate_evaluation_response,
    validate_health_response,
    validate_history_response,
    validate_interaction_response,
    validate_metrics_response,
    validate_order_detail_response,
    validate_order_summaries_response,
    validate_run_response,
    validate_scenarios_response,
    validate_shutdown_response,
    validate_synthetic_id,
    validate_system_status_response,
)
from synthetic_sales_assist.portal.lifecycle import (
    LOOPBACK_HOSTS,
    RuntimeReceipt,
    SingleInstanceLease,
    new_local_token,
    process_start_time,
)
from synthetic_sales_assist.portal.rendering import (
    render_interaction,
    render_order_detail,
    render_orders,
    render_run,
    render_safe_error,
    render_scenarios,
)


DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8765
RUNTIME_RECEIPT_FILENAME: Final = "service.json"
CSRF_HEADER: Final = "X-SSA-CSRF-Token"
SHUTDOWN_HEADER: Final = "X-SSA-Shutdown-Token"
_MAX_HEADERS: Final = 32
_MAX_HEADER_VALUE: Final = 2_048
_MAX_REJECT_DRAIN_BYTES: Final = MAX_REQUEST_BODY_BYTES + 1
_ALIAS_ROUTE = re.compile(r"\A/api/v1/scenarios/([a-z][a-z0-9-]{1,63})/instantiate\Z")
_ORDER_ROUTE = re.compile(r"\A(?:/api/v1)?/orders/(SYN-ORDER-[A-Z0-9-]+)\Z")
_ORDER_EVALUATE_ROUTE = re.compile(
    r"\A/api/v1/orders/(SYN-ORDER-[A-Z0-9-]+)/evaluate\Z"
)
_ORDER_HISTORY_ROUTE = re.compile(
    r"\A/api/v1/orders/(SYN-ORDER-[A-Z0-9-]+)/history\Z"
)
_INTERACTION_ROUTE = re.compile(
    r"\A(?:/api/v1)?/interactions/(SYN-INTERACTION-[A-Z0-9-]+)\Z"
)
_RUN_ROUTE = re.compile(r"\A(?:/api/v1)?/runs/(SYN-RUN-[A-Z0-9-]+)\Z")
_GET_ROUTES: Final = frozenset(
    {
        "/",
        "/api/v1/metrics/summary",
        "/api/v1/orders",
        "/api/v1/scenarios",
        "/api/v1/system/status",
        "/health",
        "/orders",
        "/scenarios",
        *STATIC_ASSETS,
    }
)


def _allowed_methods(path: str) -> tuple[str, ...] | None:
    if path in _GET_ROUTES:
        return ("GET",)
    if path == "/api/v1/system/shutdown":
        return ("POST",)
    if _ALIAS_ROUTE.fullmatch(path) or _ORDER_EVALUATE_ROUTE.fullmatch(path):
        return ("POST",)
    if (
        _ORDER_ROUTE.fullmatch(path)
        or _ORDER_HISTORY_ROUTE.fullmatch(path)
        or _INTERACTION_ROUTE.fullmatch(path)
        or _RUN_ROUTE.fullmatch(path)
    ):
        return ("GET",)
    return None


class PortalServerError(RuntimeError):
    """The local HTTP service could not safely start or operate."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PortalServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    def __post_init__(self) -> None:
        if type(self.host) is not str or self.host not in LOOPBACK_HOSTS:
            raise PortalServerError("PORTAL_BIND_HOST_PROHIBITED")
        if type(self.port) is not int or not 0 <= self.port <= 65_535:
            raise PortalServerError("PORTAL_PORT_INVALID")


def _status_mapping(application: ScenarioApplicationProtocol, *, deep: bool) -> dict[str, object]:
    return validate_system_status_response(application.system_status(deep=deep))


def status_is_healthy(status: dict[str, object], *, deep: bool) -> bool:
    counters = status.get("safety_counters")
    counter_values = (
        tuple(counters.values()) if type(counters) is dict else ()
    )
    accepted = frozenset({"HEALTHY", "OK", "PASS"})
    accepted_migrations = accepted | {"CURRENT"}
    database = str(status.get("database_status", "")).upper()
    migrations = str(status.get("migration_status", "")).upper()
    projections = str(status.get("projection_status", "")).upper()
    quick = str(status.get("quick_check", "")).casefold()
    integrity = status.get("integrity_check")
    return bool(
        status.get("schema_version") == "synthetic-sales-assist-application/v1"
        and type(status.get("app_version")) is str
        and bool(status.get("app_version"))
        and type(status.get("build_version")) is str
        and bool(status.get("build_version"))
        and database in accepted
        and migrations in accepted_migrations
        and projections in accepted
        and quick == "ok"
        and (not deep or str(integrity).casefold() == "ok")
        and type(status.get("database_schema_version")) is int
        and status.get("database_schema_version") == status.get("expected_schema_version")
        and type(counters) is dict
        and len(counter_values) == 9
        and all(type(value) is int and value == 0 for value in counter_values)
    )


class PortalHTTPServer(HTTPServer):
    """One bounded local listener; request execution remains single-threaded."""

    request_queue_size = 8

    def __init__(
        self,
        application: ScenarioApplicationProtocol,
        config: PortalServerConfig,
        *,
        csrf_token: str,
        shutdown_token: str,
    ) -> None:
        if (
            len(csrf_token) != 64
            or len(shutdown_token) != 64
            or csrf_token == shutdown_token
            or any(character not in "0123456789abcdef" for character in csrf_token)
            or any(character not in "0123456789abcdef" for character in shutdown_token)
        ):
            raise PortalServerError("PORTAL_CONTROL_TOKEN_INVALID")
        self.application = application
        self.csrf_token = csrf_token
        self.shutdown_token = shutdown_token
        self.shutdown_requested = threading.Event()
        self.public_host = config.host
        bind_host = DEFAULT_HOST if config.host == "localhost" else config.host
        if config.host == "::1":
            self.address_family = socket.AF_INET6
        super().__init__((bind_host, config.port), PortalRequestHandler, bind_and_activate=True)
        actual_port = int(self.server_address[1])
        authority = f"[{config.host}]" if config.host == "::1" else config.host
        self.origin = "http" + f"://{authority}:{actual_port}"
        self.expected_host = f"{authority}:{actual_port}"

    def server_bind(self) -> None:
        """Bind the validated numeric loopback address without resolver calls."""

        TCPServer.server_bind(self)
        self.server_name = self.public_host
        self.server_port = int(self.server_address[1])

    def handle_error(self, _request: object, _client_address: object) -> None:
        return


class PortalRequestHandler(BaseHTTPRequestHandler):
    """Exact-route handler with no file serving, directory listing, or debug output."""

    protocol_version = "HTTP/1.1"
    server_version = "SyntheticSalesAssist"
    sys_version = ""

    @property
    def portal_server(self) -> PortalHTTPServer:
        return cast(PortalHTTPServer, self.server)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5.0)
        self._request_body_consumed = False

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        """Replace every stdlib diagnostic response with the closed safe renderer."""

        del message, explain
        if code == 501:
            self._method_not_allowed()
            return
        self.path = getattr(self, "path", "")
        safe_codes = {
            400: "REQUEST_MALFORMED",
            414: "REQUEST_TARGET_INVALID",
            431: "REQUEST_HEADERS_INVALID",
            505: "HTTP_VERSION_UNSUPPORTED",
        }
        self._safe_error(code, safe_codes.get(code, "REQUEST_MALFORMED"))

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_HEAD(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _dispatch(self, method: str) -> None:
        try:
            path = self._validated_target()
            self._validate_common_headers()
            allowed = _allowed_methods(path)
            if allowed is None or method not in allowed:
                self._route_error(path, method)
                return
            if method == "POST":
                self._validate_post_authentication()
            if method == "GET":
                self._get(path)
            else:
                self._post(path)
        except PortalContractError as exc:
            if method == "POST" and not self._request_body_consumed:
                self._discard_bounded_body()
            self._safe_error(exc.status, exc.code)
        except PortalServerError as exc:
            self._safe_error(503, exc.code)
        except Exception as exc:
            category = str(getattr(exc, "category", ""))
            code = getattr(exc, "code", "INTERNAL_ERROR")
            statuses = {
                "INVALID": 400,
                "NOT_FOUND": 404,
                "CONFLICT": 409,
                "UNAVAILABLE": 503,
            }
            self._safe_error(statuses.get(category, 500), str(code))

    def _validated_target(self) -> str:
        target = self.path
        request_parts = self.requestline.split()
        original_target = request_parts[1] if len(request_parts) >= 2 else ""
        if (
            type(target) is not str
            or original_target != target
            or not target.startswith("/")
            or target.startswith("//")
            or "?" in target
            or "#" in target
            or "%" in target
            or "\\" in target
            or "\x00" in target
            or any(segment == ".." for segment in target.split("/"))
            or len(target) > 512
        ):
            raise PortalContractError("REQUEST_TARGET_INVALID")
        return target

    def _discard_bounded_body(self) -> None:
        """Best-effort bounded drain before closing an early-rejected POST."""

        if self.headers.get("Transfer-Encoding") is not None:
            return
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if (
            len(lengths) != 1
            or not lengths[0].isascii()
            or not lengths[0].isdigit()
        ):
            return
        length = int(lengths[0])
        if not 0 <= length <= _MAX_REJECT_DRAIN_BYTES:
            return
        self._request_body_consumed = True
        try:
            self.connection.settimeout(0.1)
            self.rfile.read(length)
        except OSError:
            pass
        finally:
            self.connection.settimeout(5.0)

    def _validate_common_headers(self) -> None:
        if len(self.headers) > _MAX_HEADERS or any(
            len(value) > _MAX_HEADER_VALUE for value in self.headers.values()
        ):
            raise PortalContractError("REQUEST_HEADERS_INVALID", status=431)
        hosts = self.headers.get_all("Host", failobj=[])
        if hosts != [self.portal_server.expected_host]:
            raise PortalContractError("HOST_HEADER_INVALID", status=400)
        if self.headers.get("Forwarded") is not None or self.headers.get(
            "X-Forwarded-Host"
        ) is not None:
            raise PortalContractError("FORWARDED_HEADER_PROHIBITED", status=400)

    def _validate_post_authentication(self) -> None:
        origins = self.headers.get_all("Origin", failobj=[])
        if origins != [self.portal_server.origin]:
            raise PortalContractError("ORIGIN_INVALID", status=403)
        supplied_csrf = self.headers.get_all(CSRF_HEADER, failobj=[])
        if len(supplied_csrf) != 1 or not hmac.compare_digest(
            supplied_csrf[0], self.portal_server.csrf_token
        ):
            raise PortalContractError("CSRF_TOKEN_INVALID", status=403)

    def _read_json_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding") is not None:
            raise PortalContractError("TRANSFER_ENCODING_PROHIBITED")
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise PortalContractError("CONTENT_LENGTH_INVALID", status=411)
        length = int(lengths[0])
        if length > MAX_REQUEST_BODY_BYTES:
            raise PortalContractError("REQUEST_BODY_TOO_LARGE", status=413)
        content_types = self.headers.get_all("Content-Type", failobj=[])
        if len(content_types) != 1 or content_types[0].casefold() not in {
            "application/json",
            "application/json; charset=utf-8",
        }:
            raise PortalContractError("CONTENT_TYPE_INVALID", status=415)
        self._request_body_consumed = True
        body = self.rfile.read(length)
        if len(body) != length:
            raise PortalContractError("REQUEST_BODY_TRUNCATED")
        return body

    def _get(self, path: str) -> None:
        application = self.portal_server.application
        if path == "/":
            self._send(303, b"", "text/plain; charset=utf-8", {"Location": "/scenarios"})
            return
        if path == "/health":
            status = _status_mapping(application, deep=False)
            healthy = status_is_healthy(status, deep=False)
            data = {"status": "PASS" if healthy else "FAIL", **status}
            self._send_json(
                200 if healthy else 503,
                data,
                validator=validate_health_response,
            )
            return
        if path == "/api/v1/scenarios":
            self._send_json(
                200,
                application.list_scenarios(),
                validator=validate_scenarios_response,
            )
            return
        if path == "/api/v1/orders":
            self._send_json(
                200,
                application.list_orders(),
                validator=validate_order_summaries_response,
            )
            return
        if path == "/api/v1/metrics/summary":
            self._send_json(
                200,
                application.metrics_summary(),
                validator=validate_metrics_response,
            )
            return
        if path == "/api/v1/system/status":
            self._send_json(
                200,
                application.system_status(deep=False),
                validator=validate_system_status_response,
            )
            return
        if path == "/scenarios":
            self._send_html(
                render_scenarios(
                    application.list_scenarios(), self.portal_server.csrf_token
                )
            )
            return
        if path == "/orders":
            self._send_html(
                render_orders(application.list_orders(), self.portal_server.csrf_token)
            )
            return
        match = _ORDER_HISTORY_ROUTE.fullmatch(path)
        if match:
            order_id = validate_synthetic_id(match.group(1), "ORDER")
            self._send_json(
                200,
                application.get_history(order_id),
                validator=partial(
                    validate_history_response,
                    expected_order_id=order_id,
                ),
            )
            return
        match = _ORDER_ROUTE.fullmatch(path)
        if match:
            order_id = validate_synthetic_id(match.group(1), "ORDER")
            order = validate_order_detail_response(
                application.get_order(order_id),
                expected_order_id=order_id,
            )
            if path.startswith("/api/"):
                self._send_json(
                    200,
                    order,
                    validator=partial(
                        validate_order_detail_response,
                        expected_order_id=order_id,
                    ),
                )
            else:
                history = validate_history_response(
                    application.get_history(order_id),
                    expected_order_id=order_id,
                )
                self._send_html(
                    render_order_detail(
                        order,
                        history,
                        application.system_status(deep=False),
                        self.portal_server.csrf_token,
                    )
                )
            return
        match = _INTERACTION_ROUTE.fullmatch(path)
        if match:
            interaction_id = validate_synthetic_id(match.group(1), "INTERACTION")
            interaction = validate_interaction_response(
                application.get_interaction(interaction_id),
                expected_interaction_id=interaction_id,
            )
            if path.startswith("/api/"):
                self._send_json(
                    200,
                    interaction,
                    validator=partial(
                        validate_interaction_response,
                        expected_interaction_id=interaction_id,
                    ),
                )
            else:
                self._send_html(
                    render_interaction(interaction, self.portal_server.csrf_token)
                )
            return
        match = _RUN_ROUTE.fullmatch(path)
        if match:
            run_id = validate_synthetic_id(match.group(1), "RUN")
            run = validate_run_response(
                application.get_run(run_id),
                expected_run_id=run_id,
            )
            if path.startswith("/api/"):
                self._send_json(
                    200,
                    run,
                    validator=partial(
                        validate_run_response,
                        expected_run_id=run_id,
                    ),
                )
            else:
                self._send_html(render_run(run, self.portal_server.csrf_token))
            return
        asset = STATIC_ASSETS.get(path)
        if asset is not None:
            content_type, body = asset
            self._send(200, body, content_type)
            return
        self._route_error(path, "GET")

    def _post(self, path: str) -> None:
        application = self.portal_server.application
        match = _ALIAS_ROUTE.fullmatch(path)
        if match:
            alias = validate_alias(match.group(1))
            request_key, mode = parse_instantiate_request(self._read_json_body())
            self._send_json(
                201,
                application.instantiate(alias, request_key=request_key, mode=mode),
                validator=partial(
                    validate_order_detail_response,
                    expected_scenario_alias=alias,
                    expected_mode=mode,
                ),
            )
            return
        match = _ORDER_EVALUATE_ROUTE.fullmatch(path)
        if match:
            order_id = validate_synthetic_id(match.group(1), "ORDER")
            request_key = parse_evaluate_request(self._read_json_body())
            health = _status_mapping(application, deep=False)
            if not status_is_healthy(health, deep=False):
                raise PortalServerError("PORTAL_EVALUATION_HEALTH_FAILED")
            order = validate_order_detail_response(
                application.get_order(order_id),
                expected_order_id=order_id,
            )
            lines = cast(list[object], order["lines"])
            allowed_line_ids = frozenset(
                cast(str, cast(dict[str, object], line)["line_id"])
                for line in lines
            )
            self._send_json(
                200,
                application.evaluate(order_id, request_key=request_key),
                validator=partial(
                    validate_evaluation_response,
                    expected_order_id=order_id,
                    expected_scenario_alias=cast(str, order["scenario_alias"]),
                    expected_rule_pack=cast(str, order["rule_pack"]),
                    allowed_line_ids=allowed_line_ids,
                ),
            )
            return
        if path == "/api/v1/system/shutdown":
            supplied_shutdown = self.headers.get_all(SHUTDOWN_HEADER, failobj=[])
            if len(supplied_shutdown) != 1 or not hmac.compare_digest(
                supplied_shutdown[0], self.portal_server.shutdown_token
            ):
                raise PortalContractError("SHUTDOWN_TOKEN_INVALID", status=403)
            parse_shutdown_request(self._read_json_body())
            self._send_json(
                202,
                {"status": "SHUTDOWN_ACCEPTED"},
                validator=validate_shutdown_response,
                before_send=self.portal_server.shutdown_requested.set,
            )
            threading.Thread(
                target=self.portal_server.shutdown,
                name="ssa-owned-shutdown",
                daemon=True,
            ).start()
            return
        self._route_error(path, "POST")

    def _route_error(self, path: str, method: str) -> None:
        allowed = _allowed_methods(path)
        if allowed is None:
            self._safe_error(404, "ROUTE_NOT_FOUND")
            return
        if method in allowed:
            self._safe_error(404, "ROUTE_NOT_FOUND")
            return
        self._safe_error(
            405,
            "METHOD_NOT_ALLOWED",
            {"Allow": ", ".join(allowed)},
        )

    def _method_not_allowed(self) -> None:
        try:
            self._validated_target()
            self._validate_common_headers()
        except PortalContractError as exc:
            self._safe_error(exc.status, exc.code)
            return
        allowed = _allowed_methods(self.path)
        if allowed is None:
            self._safe_error(404, "ROUTE_NOT_FOUND")
            return
        self._safe_error(
            405,
            "METHOD_NOT_ALLOWED",
            {"Allow": ", ".join(allowed)},
        )

    def _send_json(
        self,
        status: int,
        data: object,
        *,
        validator: Callable[[object], object],
        before_send: Callable[[], None] | None = None,
    ) -> None:
        closed = validator(data)
        body = response_bytes(closed)
        if before_send is not None:
            before_send()
        self._send(status, body, "application/json; charset=utf-8")

    def _send_html(self, body: bytes) -> None:
        self._send(200, body, "text/html; charset=utf-8")

    def _safe_error(
        self,
        status: int,
        code: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        is_json = self.path == "/health" or self.path.startswith("/api/")
        if is_json:
            body = error_bytes(code)
            content_type = "application/json; charset=utf-8"
        else:
            body = render_safe_error(code, "")
            content_type = "text/html; charset=utf-8"
        self._send(status, body, content_type, extra_headers)

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        try:
            if len(body) > MAX_RESPONSE_BODY_BYTES:
                status = 500
                extra_headers = None
                if content_type.startswith("application/json"):
                    body = error_bytes("RESPONSE_BODY_TOO_LARGE")
                    content_type = "application/json; charset=utf-8"
                else:
                    body = render_safe_error("RESPONSE_BODY_TOO_LARGE", "")
                    content_type = "text/html; charset=utf-8"
            self.close_connection = True
            self.send_response(status)
            headers = {
                "Cache-Control": "no-store, max-age=0",
                "Connection": "close",
                "Content-Length": str(len(body)),
                "Content-Security-Policy": (
                    "default-src 'none'; base-uri 'none'; connect-src 'self'; "
                    "form-action 'self'; frame-ancestors 'none'; img-src 'self'; "
                    "object-src 'none'; script-src 'self'; style-src 'self'"
                ),
                "Content-Type": content_type,
                "Cross-Origin-Opener-Policy": "same-origin",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            }
            if extra_headers:
                headers.update(extra_headers)
            for name, value in sorted(headers.items()):
                self.send_header(name, value)
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionError, OSError):
            return


class PortalRuntime:
    """Own one application, listener, process lease, and receipt lifecycle."""

    def __init__(
        self,
        application: ScenarioApplicationProtocol | None,
        *,
        paths: DataPaths,
        receipt_path: Path,
        config: PortalServerConfig,
        application_factory: Callable[[], ScenarioApplicationProtocol] | None = None,
    ) -> None:
        expected_receipt = paths.runtime / RUNTIME_RECEIPT_FILENAME
        if (
            not isinstance(receipt_path, Path)
            or not receipt_path.is_absolute()
            or receipt_path != expected_receipt
        ):
            raise PortalServerError("RUNTIME_RECEIPT_PATH_INVALID")
        if application is None and application_factory is None:
            raise PortalServerError("PORTAL_APPLICATION_FACTORY_REQUIRED")
        if application is not None and application_factory is not None:
            raise PortalServerError("PORTAL_APPLICATION_FACTORY_CONFLICT")
        self.application = application
        self.application_factory = application_factory
        self.paths = paths
        self.receipt_path = receipt_path
        self.config = config
        self.process_identity_token = new_local_token()
        self.shutdown_token = new_local_token()
        self.csrf_token = new_local_token()
        self.lease = SingleInstanceLease(receipt_path)
        self.server: PortalHTTPServer | None = None

    def start(self) -> RuntimeReceipt:
        self.lease.acquire(self.process_identity_token)
        application_created = False
        try:
            if self.application is None:
                factory = self.application_factory
                if factory is None:  # pragma: no cover - constructor invariant
                    raise PortalServerError("PORTAL_APPLICATION_FACTORY_REQUIRED")
                self.application = factory()
                application_created = True
            application = self.application
            status = _status_mapping(application, deep=True)
            if not status_is_healthy(status, deep=True):
                raise PortalServerError("PORTAL_STARTUP_HEALTH_FAILED")
            server = PortalHTTPServer(
                application,
                self.config,
                csrf_token=self.csrf_token,
                shutdown_token=self.shutdown_token,
            )
            self.server = server
            port = int(server.server_address[1])
            receipt = RuntimeReceipt(
                schema_version="synthetic-sales-assist-runtime-receipt/v1",
                pid=os.getpid(),
                process_start_time=process_start_time(),
                process_identity_token=self.process_identity_token,
                csrf_token=self.csrf_token,
                host=server.public_host,
                port=port,
                shutdown_token=self.shutdown_token,
                database_path=str(self.paths.database),
                app_version=str(status["app_version"]),
                build_version=str(status["build_version"]),
                database_schema_version=cast(int, status["database_schema_version"]),
                origin=server.origin,
            )
            self.lease.publish(receipt)
            return receipt
        except Exception:
            if self.server is not None:
                self.server.server_close()
                self.server = None
            if application_created:
                close = getattr(self.application, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()
                self.application = None
            self.lease.release()
            raise

    def serve_forever(self) -> None:
        if self.server is None:
            raise PortalServerError("PORTAL_RUNTIME_NOT_STARTED")
        try:
            self.server.serve_forever(poll_interval=0.1)
        finally:
            self.close()

    def close(self) -> None:
        server = self.server
        self.server = None
        if server is not None:
            server.server_close()
        self.lease.release()
        close = getattr(self.application, "close", None)
        if callable(close):
            close()
        self.application = None


def open_runtime(
    *,
    data_dir: Path | None,
    receipt_path: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    application: ScenarioApplicationProtocol | None = None,
) -> PortalRuntime:
    paths = resolve_data_paths(data_dir)
    if receipt_path != paths.runtime / RUNTIME_RECEIPT_FILENAME:
        raise PortalServerError("RUNTIME_RECEIPT_PATH_INVALID")
    paths.ensure_directories()
    application_factory: Callable[[], ScenarioApplicationProtocol] | None = None
    if application is None:
        def open_application() -> ScenarioApplicationProtocol:
            from synthetic_sales_assist.application import ScenarioApplication

            return ScenarioApplication.open(data_dir)

        application_factory = open_application
    return PortalRuntime(
        application,
        paths=paths,
        receipt_path=receipt_path,
        config=PortalServerConfig(host, port),
        application_factory=application_factory,
    )


__all__ = [
    "CSRF_HEADER",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "PortalHTTPServer",
    "PortalRequestHandler",
    "PortalRuntime",
    "PortalServerConfig",
    "PortalServerError",
    "RUNTIME_RECEIPT_FILENAME",
    "SHUTDOWN_HEADER",
    "open_runtime",
    "status_is_healthy",
]
