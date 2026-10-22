"""Fake upstream clients the demo builds the real app with (`create_app(clients=demo_clients())`)."""

from .clients import demo_clients

__all__ = ["demo_clients"]
