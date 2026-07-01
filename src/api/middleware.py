from __future__ import annotations

from typing import cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PAYLOAD_TOO_LARGE_BODY = b'{"detail":"Payload excede limite de tamanho"}'
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
).encode("ascii")
_SECURITY_HEADERS = (
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"content-security-policy", _CONTENT_SECURITY_POLICY),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)
_HSTS_MAX_AGE_SECONDS = 31_536_000


class BodySizeLimitExceeded(Exception):
    """Interrompe a leitura do body quando o limite configurado é excedido."""


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit_bytes: int,
        admin_login_limit_bytes: int,
        webhook_limit_bytes: int,
    ) -> None:
        self.app = app
        self.default_limit_bytes = _require_positive(
            "API_MAX_BODY_BYTES", default_limit_bytes
        )
        self.admin_login_limit_bytes = _require_positive(
            "ADMIN_LOGIN_MAX_BODY_BYTES", admin_login_limit_bytes
        )
        self.webhook_limit_bytes = _require_positive(
            "WEBHOOK_MAX_BODY_BYTES", webhook_limit_bytes
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit_bytes = self._limit_for(scope)
        content_length = _content_length(scope)
        if content_length is not None and content_length > limit_bytes:
            await _send_payload_too_large(send)
            return

        consumed_bytes = 0
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def receive_wrapper() -> Message:
            nonlocal consumed_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    consumed_bytes += len(body)
                    if consumed_bytes > limit_bytes:
                        raise BodySizeLimitExceeded
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except BodySizeLimitExceeded:
            if not response_started:
                await _send_payload_too_large(send)

    def _limit_for(self, scope: Scope) -> int:
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))

        if method == "POST" and path == "/admin/login":
            return self.admin_login_limit_bytes
        if path == "/api/v1/openclaw/telegram-event":
            return self.webhook_limit_bytes
        return self.default_limit_bytes


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        self.app = app
        self.hsts_enabled = hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = _message_headers(message)
                for name, value in _SECURITY_HEADERS:
                    _set_header(headers, name, value)
                if self.hsts_enabled and _is_https(scope):
                    _set_header(
                        headers,
                        b"strict-transport-security",
                        (
                            f"max-age={_HSTS_MAX_AGE_SECONDS}; "
                            "includeSubDomains"
                        ).encode("ascii"),
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _require_positive(name: str, value: int) -> int:
    if value <= 0:
        raise ValueError(f"{name} deve ser maior que zero")
    return value


def _content_length(scope: Scope) -> int | None:
    for name, value in _scope_headers(scope):
        if name.lower() != b"content-length":
            continue
        try:
            return int(value.decode("ascii"))
        except ValueError:
            return None
    return None


def _is_https(scope: Scope) -> bool:
    if str(scope.get("scheme", "")).lower() == "https":
        return True

    for name, value in _scope_headers(scope):
        if name.lower() != b"x-forwarded-proto":
            continue
        forwarded_proto = value.split(b",", 1)[0].strip().lower()
        return forwarded_proto == b"https"
    return False


def _scope_headers(scope: Scope) -> list[tuple[bytes, bytes]]:
    headers = scope.get("headers", [])
    if not isinstance(headers, list):
        return []
    return cast(list[tuple[bytes, bytes]], headers)


def _message_headers(message: Message) -> list[tuple[bytes, bytes]]:
    headers = message.setdefault("headers", [])
    if not isinstance(headers, list):
        headers = []
        message["headers"] = headers
    return cast(list[tuple[bytes, bytes]], headers)


def _set_header(headers: list[tuple[bytes, bytes]], name: bytes, value: bytes) -> None:
    header_name = name.lower()
    for index, (existing_name, _existing_value) in enumerate(headers):
        if existing_name.lower() == header_name:
            headers[index] = (existing_name, value)
            return
    headers.append((name, value))


async def _send_payload_too_large(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_PAYLOAD_TOO_LARGE_BODY)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _PAYLOAD_TOO_LARGE_BODY})
