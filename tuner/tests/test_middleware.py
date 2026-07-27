from collections.abc import Iterator

from api.middleware import RequestSizeLimitMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


async def _consume_body(request: Request) -> JSONResponse:
    return JSONResponse({"size": len(await request.body())})


def test_streamed_request_cannot_bypass_size_limit() -> None:
    app = Starlette(routes=[Route("/", _consume_body, methods=["POST"])])
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=3)

    def chunks() -> Iterator[bytes]:
        yield b"ab"
        yield b"cd"

    response = TestClient(app).post("/", content=chunks())

    assert response.status_code == 413
