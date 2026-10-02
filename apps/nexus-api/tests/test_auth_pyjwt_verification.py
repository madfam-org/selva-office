"""End-to-end verification of Janua tokens in ``nexus_api.auth.verify_jwt``.

Real RS256 tokens are signed with throwaway RSA keys and verified against a
JWKS built from their public halves. Only the JWKS HTTP fetch is stubbed, so
these tests exercise PyJWT's signature, algorithm and claim checks as
``verify_jwt`` configures them: key selection by ``kid``, the fixed
``["RS256"]`` allow-list, required ``exp``/``iss``/``aud`` and a 30 s leeway.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from nexus_api import auth as _auth_mod
from nexus_api.config import Settings

_ISSUER = "https://janua.example.com"
_AUDIENCE = "selva-office"

_KEY_A = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KEY_B = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KEY_UNPUBLISHED = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_EC_KEY = ec.generate_private_key(ec.SECP256R1())


def _rsa_jwk(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return jwk


def _ec_jwk(private_key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, Any]:
    jwk: dict[str, Any] = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "use": "sig"})
    return jwk


_JWKS = {"keys": [_rsa_jwk(_KEY_A, "key-a"), _rsa_jwk(_KEY_B, "key-b")]}


def _settings() -> MagicMock:
    s = MagicMock(spec=Settings)
    s.janua_issuer_url = _ISSUER
    s.janua_client_id = _AUDIENCE
    return s


def _claims(**overrides: Any) -> dict[str, Any]:
    """Janua-shaped access-token claims; an override of ``None`` drops the claim."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "user-1",
        "email": "user@example.com",
        "org_id": "org-1",
        "roles": ["tactician"],
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + 900,
        "jti": "jti-1",
    }
    for name, value in overrides.items():
        if value is None:
            claims.pop(name, None)
        else:
            claims[name] = value
    return claims


def _token(
    private_key: Any = _KEY_A,
    kid: str | None = "key-a",
    algorithm: str = "RS256",
    **overrides: Any,
) -> str:
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(_claims(**overrides), private_key, algorithm=algorithm, headers=headers)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unsigned_token(header: dict[str, Any]) -> str:
    """A token with ``alg: none`` and an empty signature, built by hand."""
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(_claims()).encode())}"
    return f"{signing_input}."


def _hs256_with_public_key_token(public_key: rsa.RSAPublicKey, kid: str) -> str:
    """Algorithm confusion: HS256 keyed with the published RSA public key.

    Built by hand because PyJWT refuses to HMAC-sign with a PEM key.
    """
    secret = public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(_claims()).encode())}"
    signature = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


@pytest.fixture(autouse=True)
def _clear_jwks_cache() -> None:
    _auth_mod._jwks_cache = None
    _auth_mod._jwks_cache_time = None


async def _verify(token: str, jwks: dict[str, Any] | None = None) -> dict[str, Any]:
    with patch.object(_auth_mod, "_fetch_jwks", AsyncMock(return_value=jwks or _JWKS)):
        return await _auth_mod.verify_jwt(token, _settings())


async def _assert_rejected(token: str, jwks: dict[str, Any] | None = None) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _verify(token, jwks)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired token"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
class TestValidTokens:
    async def test_valid_token_returns_payload(self) -> None:
        payload = await _verify(_token())
        assert payload["sub"] == "user-1"
        assert payload["org_id"] == "org-1"
        assert payload["roles"] == ["tactician"]

    async def test_key_is_selected_by_kid(self) -> None:
        payload = await _verify(_token(private_key=_KEY_B, kid="key-b"))
        assert payload["sub"] == "user-1"

    async def test_audience_list_containing_client_id(self) -> None:
        payload = await _verify(_token(aud=["other-api", _AUDIENCE]))
        assert payload["sub"] == "user-1"

    async def test_expired_within_leeway_is_accepted(self) -> None:
        now = int(time.time())
        payload = await _verify(_token(iat=now - 900, exp=now - 10))
        assert payload["sub"] == "user-1"

    async def test_iat_slightly_in_future_is_accepted(self) -> None:
        payload = await _verify(_token(iat=int(time.time()) + 10))
        assert payload["sub"] == "user-1"


@pytest.mark.asyncio
class TestKeySelection:
    async def test_unknown_kid_rejected(self) -> None:
        await _assert_rejected(_token(kid="key-rotated-away"))

    async def test_missing_kid_rejected(self) -> None:
        await _assert_rejected(_token(kid=None))

    async def test_kid_of_other_key_rejected(self) -> None:
        # Signed with key A but names key B: the kid's key must verify it.
        await _assert_rejected(_token(private_key=_KEY_A, kid="key-b"))

    async def test_forged_signature_rejected(self) -> None:
        await _assert_rejected(_token(private_key=_KEY_UNPUBLISHED, kid="key-a"))

    async def test_tampered_payload_rejected(self) -> None:
        header, _payload, signature = _token().split(".")
        forged = _b64(json.dumps(_claims(roles=["admin"])).encode())
        await _assert_rejected(f"{header}.{forged}.{signature}")

    async def test_non_rsa_jwk_rejected_as_401(self) -> None:
        jwks = {"keys": [_ec_jwk(_EC_KEY, "key-ec")]}
        await _assert_rejected(_token(private_key=_EC_KEY, kid="key-ec", algorithm="ES256"), jwks)

    async def test_jwk_with_other_alg_rejected(self) -> None:
        jwk = _rsa_jwk(_KEY_A, "key-a")
        jwk["alg"] = "RS512"
        await _assert_rejected(_token(), {"keys": [jwk]})

    async def test_malformed_token_rejected(self) -> None:
        await _assert_rejected("not-a-jwt")


@pytest.mark.asyncio
class TestAlgorithmAllowList:
    async def test_alg_none_rejected(self) -> None:
        await _assert_rejected(_unsigned_token({"alg": "none", "typ": "JWT", "kid": "key-a"}))

    async def test_hs256_signed_with_public_key_rejected(self) -> None:
        await _assert_rejected(_hs256_with_public_key_token(_KEY_A.public_key(), "key-a"))

    async def test_rs512_rejected(self) -> None:
        await _assert_rejected(_token(algorithm="RS512"))

    async def test_es256_rejected(self) -> None:
        await _assert_rejected(_token(private_key=_EC_KEY, kid="key-a", algorithm="ES256"))


@pytest.mark.asyncio
class TestClaims:
    async def test_expired_rejected(self) -> None:
        now = int(time.time())
        await _assert_rejected(_token(iat=now - 3600, exp=now - 600))

    async def test_missing_exp_rejected(self) -> None:
        await _assert_rejected(_token(exp=None))

    async def test_wrong_audience_rejected(self) -> None:
        await _assert_rejected(_token(aud="another-api"))

    async def test_missing_audience_rejected(self) -> None:
        await _assert_rejected(_token(aud=None))

    async def test_wrong_issuer_rejected(self) -> None:
        await _assert_rejected(_token(iss="https://evil.example.com"))

    async def test_missing_issuer_rejected(self) -> None:
        await _assert_rejected(_token(iss=None))

    async def test_not_yet_valid_rejected(self) -> None:
        await _assert_rejected(_token(nbf=int(time.time()) + 600))

    async def test_iat_far_in_future_rejected(self) -> None:
        now = int(time.time())
        await _assert_rejected(_token(iat=now + 600, exp=now + 1200))
