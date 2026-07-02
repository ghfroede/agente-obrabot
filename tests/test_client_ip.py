from __future__ import annotations

from unittest.mock import MagicMock

from src.api.deps import client_ip


def test_client_ip_uses_first_forwarded_hop() -> None:
    request = MagicMock()
    request.headers = {"x-forwarded-for": "203.0.113.1, 10.0.0.1"}
    request.client = MagicMock(host="127.0.0.1")
    assert client_ip(request) == "203.0.113.1"


def test_client_ip_falls_back_to_direct_client() -> None:
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="192.168.1.5")
    assert client_ip(request) == "192.168.1.5"
