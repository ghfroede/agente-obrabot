from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path("openclaw/config")
EXPECTED_SUBAGENTS = [
    "triagem",
    "rdo",
    "fotos",
    "orcamento",
    "cronograma",
    "medicoes",
    "documentos",
]
EXPECTED_SKILLS = [
    "obrabot-api",
    "ingestao-telegram",
    "triagem-obra",
    "rdo",
    "fotos",
    "orcamento",
    "cronograma",
    "medicoes",
    "documentos",
]
EXPECTED_TOOL_ALLOW = [
    "agents_list",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
]
EXPECTED_PLUGIN_ALLOW = [
    "browser",
    "canvas",
    "codex",
    "device-pair",
    "file-transfer",
    "memory-core",
    "openai",
    "phone-control",
    "talk-voice",
    "telegram",
]
CONFIG_NAMES = [
    "openclaw.json",
    "openclaw.example.json",
    "openclaw.production.example.json",
]


def _load_config(name: str) -> dict[str, object]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def test_openclaw_configs_use_hmac_contract() -> None:
    for name in CONFIG_NAMES:
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


def test_openclaw_configs_expose_ceo_subagents() -> None:
    for name in CONFIG_NAMES:
        config = _load_config(name)

        skills = config["skills"]
        assert isinstance(skills, dict)
        assert skills["allowExternal"] is False
        assert skills["enabled"] == EXPECTED_SKILLS

        tools = config["tools"]
        assert isinstance(tools, dict)
        assert tools["profile"] == "coding"
        assert tools["alsoAllow"] == EXPECTED_TOOL_ALLOW

        plugins = config["plugins"]
        assert isinstance(plugins, dict)
        assert plugins["bundledDiscovery"] == "allowlist"
        assert plugins["allow"] == EXPECTED_PLUGIN_ALLOW

        agents = config["agents"]
        assert isinstance(agents, dict)
        assert set(agents) == {"ceo", *EXPECTED_SUBAGENTS}

        ceo = agents["ceo"]
        assert isinstance(ceo, dict)
        assert ceo["skills"] == ["obrabot-api", "ingestao-telegram", "triagem-obra"]
        assert ceo["subagents"] == EXPECTED_SUBAGENTS

        for agent_id in EXPECTED_SUBAGENTS:
            agent = agents[agent_id]
            assert isinstance(agent, dict)
            assert agent["workspace"] == f"./openclaw/agents/{agent_id}"
            assert "obrabot-api" in agent["skills"]
