"""Courier envelope: existing contract by default; threading only when enabled."""

from __future__ import annotations

from selva_autoheal import courier
from selva_autoheal.testing import FakeCourier, make_cfg

ENV = {"COURIER_API_KEY": "producer-key-placeholder"}


async def test_not_configured_sends_nothing() -> None:
    fake = FakeCourier()
    delivery = await courier.send(make_cfg(courier_recipient=""), text="t",
                                  idempotency_key="k", post=fake, env=ENV)
    assert delivery.status == "not_configured" and fake.sent == []


async def test_missing_producer_key_sends_nothing() -> None:
    fake = FakeCourier()
    delivery = await courier.send(make_cfg(), text="t", idempotency_key="k", post=fake, env={})
    assert delivery.status == "not_configured" and fake.sent == []


async def test_reply_to_only_with_threading_enabled() -> None:
    off = courier.build_envelope(make_cfg(), text="t", idempotency_key="k", urgent=True,
                                 reply_to="dlv-1")
    on = courier.build_envelope(make_cfg(courier_threading=True), text="t",
                                idempotency_key="k", urgent=False, reply_to="dlv-1")
    assert "reply_to" not in off and off["priority"] == "urgent"
    assert on["reply_to"] == {"delivery_id": "dlv-1"} and on["priority"] == "normal"


async def test_rejection_and_replay_are_reported() -> None:
    rejected = await courier.send(make_cfg(), text="t", idempotency_key="k",
                                  post=FakeCourier(status=400), env=ENV)
    replayed = await courier.send(make_cfg(), text="t", idempotency_key="k",
                                  post=FakeCourier(status=200), env=ENV)
    assert (rejected.sent, rejected.status) == (False, "rejected")
    assert (replayed.sent, replayed.status) == (True, "replayed")


async def test_transport_error_is_an_outcome() -> None:
    async def boom(url: str, headers: dict[str, str], body: dict[str, object]) -> tuple[int, object]:
        raise ConnectionError("down")

    delivery = await courier.send(make_cfg(), text="t", idempotency_key="k", post=boom, env=ENV)
    assert (delivery.sent, delivery.status) == (False, "error")
