"""The gateway's own last look at a pseudonymized payload.

``find_direct_identifiers`` backs the pseudonymized-task exception: before an
excepted request reaches a cloud provider, the gateway refuses it if it
carries an obvious direct identifier. These tests pin what counts as obvious
(e-mail, phone, CURP, RFC, non-text content), what must NOT trip it (dates,
times, scores, amounts, ids that are not personal), and that the result
names kinds only — never the matching text.

All identifiers below are synthetic.
"""

from __future__ import annotations

from typing import Any

import pytest

from madfam_inference.identifier_guard import (
    CURP,
    EMAIL,
    KIND_LABELS,
    NON_TEXT_CONTENT,
    PHONE,
    RFC,
    find_direct_identifiers,
)


def _scan(text: str) -> list[str]:
    return find_direct_identifiers([{"role": "user", "content": text}])


class TestFindsObviousIdentifiers:
    @pytest.mark.parametrize(
        "text",
        [
            "Escribe a ana.lopez@example.com cuando puedas",
            "contacto: tutor+retro@correo.example.mx",
            "MAYUSCULAS@EXAMPLE.ORG",
        ],
    )
    def test_email(self, text: str) -> None:
        assert _scan(text) == [EMAIL]

    @pytest.mark.parametrize(
        "text",
        [
            "Tel. 777 123 4567",
            "llamar al (777) 123-4567",
            "+52 1 777 123 4567",
            "+52 777 123 4567",
            "0052 777 123 4567",
            "55-1234-5678",
            "55 12 34 56 78",
            "cel 7771234567",
            "+1 (555) 123-4567",
            "777.123.4567",
        ],
    )
    def test_phone(self, text: str) -> None:
        assert _scan(text) == [PHONE]

    @pytest.mark.parametrize(
        "text",
        ["CURP GODE561231HDFRRN09", "curp: gode561231hdfrrn09.", "(XEXX010101HNEXXXA4)"],
    )
    def test_curp(self, text: str) -> None:
        assert _scan(text) == [CURP]

    @pytest.mark.parametrize(
        "text",
        ["RFC GODE561231AB1", "rfc de la empresa: ABC010203XY9", "su RFC es ñaco800101k5a"],
    )
    def test_rfc(self, text: str) -> None:
        assert _scan(text) == [RFC]

    def test_a_curp_is_reported_once_as_a_curp(self) -> None:
        """A CURP starts with an RFC-shaped prefix; it must not also count as
        an RFC (the refusal message would be wrong)."""
        assert _scan("GODE561231HDFRRN09") == [CURP]

    @pytest.mark.parametrize(
        "block",
        [
            {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            {"type": "image_base64", "content": "iVBORw0KGgo=", "mime_type": "image/png"},
            {"type": "input_audio", "input_audio": {"data": "UklGR", "format": "wav"}},
            {"no_type": "x"},
            42,
        ],
    )
    def test_non_text_content(self, block: Any) -> None:
        messages = [{"role": "user", "content": [{"type": "text", "text": "hola"}, block]}]
        assert NON_TEXT_CONTENT in find_direct_identifiers(messages)

    def test_several_kinds_are_all_reported_sorted(self) -> None:
        found = _scan("ana@example.com, 777 123 4567, GODE561231HDFRRN09, GODE561231AB1")
        assert found == sorted([EMAIL, PHONE, CURP, RFC])


class TestScansTheWholePayload:
    def test_system_prompt(self) -> None:
        messages = [
            {"role": "system", "content": "Responde a ana@example.com"},
            {"role": "user", "content": "texto limpio"},
        ]
        assert find_direct_identifiers(messages) == [EMAIL]

    def test_text_blocks_in_either_shape(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "OpenAI shape 777 123 4567"},
                    {"type": "text", "content": "Selva shape GODE561231HDFRRN09"},
                ],
            }
        ]
        assert find_direct_identifiers(messages) == [CURP, PHONE]

    def test_name_field_and_tool_arguments(self) -> None:
        messages = [
            {"role": "user", "name": "ana@example.com", "content": "hola"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": "f", "arguments": '{"rfc": "GODE561231AB1"}'}}
                ],
            },
        ]
        assert find_direct_identifiers(messages) == [EMAIL, RFC]

    def test_clean_payload_returns_nothing(self) -> None:
        messages = [
            {"role": "system", "content": "Eres asistente de redacción."},
            {"role": "user", "content": "[PERSONA_1] trabajó con atención en 3 actividades."},
        ]
        assert find_direct_identifiers(messages) == []


class TestDoesNotTripOnOrdinaryText:
    @pytest.mark.parametrize(
        "text",
        [
            "Sesión del 2026-10-07 10:30 con avances",
            "2026-10-07T10:30:00Z",
            "07/10/2026 a las 16:45",
            "07-10-2026, de 09:00 a 10:30:15",
            "Puntajes 8 9 7 10 9 8 7 9 10 8",
            "Costo $1,500.00 MXN, folio 12345",
            "e6cbd51d-8329-4c4e-8c74-aba643ab4575",
            "Del 1 al 15 de octubre de 2026 trabajó 3 actividades",
            "@persona mencionó algo; correo pendiente",
            "Actividad 1: rompecabezas de 12 piezas en 10 minutos",
            "Edad 7 años, 3 meses; 2 sesiones por semana",
            "Logró 100% en 2 de 3 intentos (66.7%)",
            "😊 Estado de ánimo y regulación emocional",
        ],
    )
    def test_no_false_positive(self, text: str) -> None:
        assert _scan(text) == []


class TestNeverReturnsTheMatch:
    def test_result_is_kinds_only(self) -> None:
        secret_email = "persona.secreta@example.com"
        secret_phone = "777 987 6543"
        found = _scan(f"{secret_email} {secret_phone}")
        rendered = repr(found) + " ".join(KIND_LABELS[kind] for kind in found)
        assert secret_email not in rendered
        assert "987" not in rendered
        assert set(found) <= set(KIND_LABELS)

    def test_tolerates_odd_shapes(self) -> None:
        assert find_direct_identifiers([]) == []
        assert find_direct_identifiers(None) == []
        assert find_direct_identifiers([{"role": "user"}]) == []
        assert find_direct_identifiers(["777 123 4567"]) == [PHONE]
