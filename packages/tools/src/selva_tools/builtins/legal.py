"""Legal tools -- contract generation, REPSE check, law search, compliance."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class ContractGenerateTool(BaseTool):
    name = "contract_generate"
    description = (
        "Generate a legal contract via the Karafiel CLM module "
        "(NDA, prestacion de servicios, compraventa, arrendamiento)"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "contract_type": {
                    "type": "string",
                    "description": (
                        "Contract type: nda, prestacion_servicios, compraventa, arrendamiento"
                    ),
                    "enum": [
                        "nda",
                        "prestacion_servicios",
                        "compraventa",
                        "arrendamiento",
                    ],
                },
                "parties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "rfc": {"type": "string"},
                            "role": {"type": "string"},
                        },
                        "required": ["name", "rfc", "role"],
                    },
                    "description": "Contracting parties with name, RFC, and role",
                },
                "terms": {
                    "type": "object",
                    "description": "Contract terms (duration, amount, conditions, etc.)",
                },
                "locale": {
                    "type": "string",
                    "default": "es-MX",
                    "description": "Locale for the contract language",
                },
            },
            "required": ["contract_type", "parties"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        contract_type: str = kwargs.get("contract_type", "")
        parties: list[dict[str, Any]] = kwargs.get("parties", [])
        terms: dict[str, Any] = kwargs.get("terms", {})
        locale: str = kwargs.get("locale", "es-MX")

        if not contract_type or not parties:
            return ToolResult(success=False, error="contract_type and parties are required")

        adapter = KarafielAdapter()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{adapter._base_url}/api/v1/contracts/generate/",
                    headers=adapter._headers(),
                    json={
                        "contract_type": contract_type,
                        "parties": parties,
                        "terms": terms,
                        "locale": locale,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return ToolResult(
                    success=True,
                    output=(
                        f"Contract generated: id={data.get('contract_id', 'N/A')}, "
                        f"url={data.get('document_url', 'N/A')}"
                    ),
                    data=data,
                )
        except Exception as exc:
            return ToolResult(success=False, error=f"Contract generation failed: {exc}")


class REPSECheckTool(BaseTool):
    name = "repse_check"
    description = (
        "Verify REPSE (Registro de Prestadoras de Servicios Especializados) "
        "registration status for an RFC via Karafiel"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": "RFC of the service provider to verify",
                },
                "service_type": {
                    "type": "string",
                    "description": "Type of specialized service being provided",
                },
            },
            "required": ["rfc"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        rfc: str = kwargs.get("rfc", "")
        service_type: str = kwargs.get("service_type", "")

        if not rfc:
            return ToolResult(success=False, error="rfc is required")

        adapter = KarafielAdapter()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{adapter._base_url}/api/v1/compliance/repse/check/",
                    headers=adapter._headers(),
                    json={"rfc": rfc, "service_type": service_type},
                )
                resp.raise_for_status()
                data = resp.json()
                registered = data.get("registered", False)
                return ToolResult(
                    success=True,
                    output=(
                        f"REPSE check for {rfc}: registered={registered}, "
                        f"number={data.get('registration_number', 'N/A')}, "
                        f"expiry={data.get('expiry', 'N/A')}"
                    ),
                    data=data,
                )
        except Exception as exc:
            return ToolResult(success=False, error=f"REPSE check failed: {exc}")


class LawSearchTool(BaseTool):
    name = "law_search"
    description = "Search Mexican laws and regulations via the Tezca legal intelligence API"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for law articles",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum number of results to return",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.tezca import TezcaAdapter

        query: str = kwargs.get("query", "")
        limit: int = kwargs.get("limit", 5)

        if not query:
            return ToolResult(success=False, error="query is required")

        adapter = TezcaAdapter()
        articles = await adapter.search_laws(query=query, limit=limit)

        if not articles:
            return ToolResult(
                success=True,
                output=f"No articles found for query: {query}",
                data={"articles": [], "count": 0},
            )

        summaries = [f"{a.ley} Art. {a.articulo}: {a.titulo}" for a in articles]
        return ToolResult(
            success=True,
            output=f"Found {len(articles)} article(s):\n" + "\n".join(summaries),
            data={
                "articles": [a.model_dump() for a in articles],
                "count": len(articles),
            },
        )


class ComplianceCheckTool(BaseTool):
    name = "compliance_check"
    description = (
        "Run a regulatory compliance check for a business domain "
        "(laboral, fiscal, mercantil, datos_personales) via Tezca"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": (
                        "Compliance domain: laboral, fiscal, mercantil, datos_personales"
                    ),
                    "enum": [
                        "laboral",
                        "fiscal",
                        "mercantil",
                        "datos_personales",
                    ],
                },
                "context": {
                    "type": "object",
                    "description": "Additional context for the compliance evaluation",
                },
            },
            "required": ["domain"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.tezca import TezcaAdapter

        domain: str = kwargs.get("domain", "")
        context: dict[str, Any] = kwargs.get("context", {})

        if not domain:
            return ToolResult(success=False, error="domain is required")

        adapter = TezcaAdapter()
        result = await adapter.check_compliance(domain=domain, context=context)

        status_label = "compliant" if result.compliant else "non-compliant"
        issues_text = f" Issues: {', '.join(result.issues)}" if result.issues else ""
        return ToolResult(
            success=True,
            output=f"Compliance check ({domain}): {status_label}.{issues_text}",
            data=result.model_dump(),
        )
