"""Fixtures for the autoheal tests. Doubles live in ``selva_autoheal.testing``.

No test reaches a network, a cluster, a model provider or a chat.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio

from selva_autoheal.testing import RecordedEnclii

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def enclii_responses() -> dict[str, Any]:
    responses = load("cnpg_operator_ingress_2026-10-24.enclii.json")
    responses.pop("_note", None)
    return dict(responses)


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def alert_payload() -> dict[str, Any]:
    return load("cnpg_operator_ingress_2026-10-24.alertmanager.json")


@pytest.fixture
def enclii() -> RecordedEnclii:
    return RecordedEnclii(enclii_responses())
