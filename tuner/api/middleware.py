"""ASGI middleware for rejecting oversized requests before multipart parsing."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import ApiError


class _RequestTooLargeError(Exception):
    pass


class RequestSizeLimitMiddleware:
    """Enforce an aggregate request-body limit before route parsing."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        """Configure the wrapped ASGI app and byte limit."""
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject HTTP requests whose aggregate body exceeds the limit."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestTooLargeError:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = ApiError(413, "Request body is too large.", "urn:mddash:payload-too-large").to_response()
        await response(scope, receive, send)
