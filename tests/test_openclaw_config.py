from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path("openclaw/config")


def _load_config(name: str) -> dict[str, object]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def test_openclaw_configs_use_hmac_contract() -> None:
    for name in [
        "openclaw.json",
        "openclaw.example.json",
        "openclaw.production.example.json",
    ]:
        config = _load_config(name)
        backend = config["backend"]
        assert isinstance(backend, dict)
        assert "sharedSecretHeader" not in backend
        assert "sharedSecret" not in backend

        hmac_config = backend["hmac"]
        assert isinstance(hmac_config, dict)
        assert hmac_config["enabled"] is True
        assert hmac_config["secret"] == "${OPENCLAW_SHARED_SECRET}"
        assert hmac_config["signatureHeader"] == "X-OpenClaw-Signature"
        assert hmac_config["timestampHeader"] == "X-OpenClaw-Timestamp"
        assert hmac_config["eventIdHeader"] == "X-OpenClaw-Event-Id"
