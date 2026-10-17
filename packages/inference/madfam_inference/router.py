from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from . import grants as _grants
from .base import InferenceProvider, UsageCallback
from .caching import PromptCacheManager
from .types import InferenceRequest, InferenceResponse, RoutingPolicy, Sensitivity, StreamUsage

logger = logging.getLogger(__name__)
_cache_manager = PromptCacheManager()


def _budget_gate_enabled() -> bool:
    return os.environ.get("BUDGET_GATE_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )


def _try_import_budget_gate() -> Any:
    """Best-effort lazy import of the budget gate.

    Returns ``None`` (and logs once) when the package isn't installed.
    The integration is intentionally optional — the gate is a
    bedrock-safety opt-in, not a hard dependency of the inference
    router.
    """
    try:
        import madfam_budget_gate

        return madfam_budget_gate
    except ImportError:
        logger.warning(
            "budget-gate: BUDGET_GATE_ENABLED is set but madfam-budget-gate "
            "package is not installed; gate is disabled"
        )
        return None


def _is_hard_failure(exc: BaseException) -> bool:
    """Return True when the exception should NOT trigger fallback, because
    the same request would fail identically against any other provider.

    Hard failures (re-raised, never retried, never fallen back from):
      - HTTP 401 (auth) — wrong/missing API key, surface so ops rotates.
        Silently switching to another provider that is ALSO at $0 just
        masks the alarm.
      - HTTP 403 (forbidden) — model/region blocked, would block elsewhere.
      - HTTP 404 (model not found) — bad model id, would 404 elsewhere.
      - HTTP 422 (unprocessable entity) — request-body validation error,
        same payload will fail elsewhere.

    Everything else is fallback-eligible and falls through to the next
    provider in cloud_priority. In particular:
      - HTTP 400 (the load-bearing case: Anthropic returns 400 with
        "credit balance too low" when $0 credits — must fall back, not
        be treated as "request malformed" and silently ship placeholder).
      - HTTP 429 (rate-limited) — fall back to a different vendor rather
        than block the worker on back-off.
      - HTTP 5xx — provider transient.
      - Network errors / timeouts — provider transient.
      - Plain RuntimeError from legacy adapters — preserve existing
        broad-catch fallback behaviour, BUT recognise 'rate-limit' /
        'credit balance' / 'insufficient_quota' embedded in the message
        as fallback-eligible (some providers wrap their HTTP responses
        in RuntimeError before it reaches us).

    The classifier is defensive: when in doubt, fall back. The cost of
    an extra provider hop is far smaller than the cost of returning a
    placeholder string to a worker that will then ship it.
    """
    # Adapter errors that are an answer, not an outage (e.g. a model
    # refusal): re-sending to another vendor would launder the refusal.
    if getattr(exc, "no_fallback", False):
        return True

    try:
        import httpx
    except ImportError:  # pragma: no cover — httpx is a hard dep elsewhere
        return False

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        # 401/403/404/422 — surface; everything else falls back.
        if status in (401, 403, 404, 422):
            return True

    # Recognise embedded auth-style status in plain error messages —
    # only when the message clearly says "401" / "auth" / "unauthorized"
    # and DOES NOT also say "rate" / "credit" / "quota". This mirrors
    # the HTTPStatusError branch above for adapters that don't preserve
    # the structured exception.
    msg = str(exc).lower()
    auth_signal = (
        "401" in msg
        or "unauthorized" in msg
        or "invalid api key" in msg
        or "invalid_api_key" in msg
    )
    quota_signal = "rate" in msg or "credit" in msg or "quota" in msg
    return auth_signal and not quota_signal


def _cache_cost_kwargs(
    provider: str | None,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> dict[str, float]:
    """``actual_cost_usd`` for ``gate.record`` when the call used the prompt cache.

    Without cache tokens this returns ``{}`` and the gate estimates the cost
    itself, exactly as before.
    """
    if cache_read_tokens <= 0 and cache_creation_tokens <= 0:
        return {}
    from madfam_budget_gate import estimate_cost  # only reached with the gate armed

    return {
        "actual_cost_usd": estimate_cost(
            provider,
            model,
            input_tokens,
            output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )
    }


def _is_fallback_eligible(exc: BaseException) -> bool:
    """Inverse of _is_hard_failure — kept as a named helper because the
    test suite documents desired classifier behaviour against this name.

    Network/transient/4xx-non-auth/5xx all return True. 401/403/404/422
    return False. Bare RuntimeError("something broke") returns True
    (broad fallback preserved — see _is_hard_failure for rationale).
    """
    return not _is_hard_failure(exc)




# Provider names expected by the router.  The keys in the providers dict
# passed to ModelRouter should use these identifiers.
LOCAL_PROVIDER = "ollama"
# Sensitivity levels that may ONLY be served by the local provider.
# This is the data-residency boundary the ecosystem contract rests on
# (clinical notes on minors, CFDI, payroll): the request's data must
# never reach a third-party cloud vendor.
LOCAL_ONLY_SENSITIVITIES = (Sensitivity.RESTRICTED, Sensitivity.CONFIDENTIAL)
CLOUD_PRIORITY = [
    "anthropic",
    "openai",
    "groq",
    "mistral",
    "moonshot",
    "siliconflow",
    "fireworks",
    "together",
    "deepinfra",
    "openrouter",
]
CHEAPEST_PRIORITY = [
    "deepinfra",
    "groq",
    "together",
    "siliconflow",
    "fireworks",
    "mistral",
    "moonshot",
    "openrouter",
    "openai",
    "anthropic",
]


class ModelRouter:
    """Routes inference requests to providers based on sensitivity policy.

    **Sensitivity is evaluated FIRST and is never overridable.** The
    allowed provider set for the request's sensitivity level is computed
    before anything else; every later rule can only pick *within* that
    set, never outside it.

    Routing rules (applied in order):
    1. **Sensitivity gate** — compute the allowed provider set:
       ``restricted`` / ``confidential`` -> ``[LOCAL_PROVIDER]`` only;
       ``internal`` -> CLOUD_PRIORITY; ``public`` -> CHEAPEST_PRIORITY.
       ``require_local=True`` narrows the set to the local provider.
       A server-set ``provider_allowlist`` (a tenant task exception)
       narrows a cloud-eligible request to the allowlist intersected with
       CLOUD_PRIORITY, in the allowlist's order; it never applies to
       ``restricted`` / ``confidential`` / ``require_local``.
    2. ``task_type`` — if the org config has a model assignment for the
       request's task type **and that assignment's provider is inside the
       allowed set**, jump to it and override the model name. An
       assignment pointing outside the allowed set is REFUSED (logged at
       WARNING) and routing falls through to the sensitivity-derived
       candidates. This is what stops a ``model_assignments`` entry from
       silently sending clinical ``restricted`` data to a cloud vendor.
       Under a ``provider_allowlist`` assignments are not consulted at all:
       the exception pins its own providers, order and models.
    3. Otherwise take the first registered provider in the allowed set.
    4. ``prefer_local=True`` moves the local provider first *within* the
       allowed set (it can never add it to a set that excludes it). It is
       ignored under a ``provider_allowlist``, which is exact.

    If no provider in the allowed set is registered, the router raises —
    it never widens the set to find something that answers.
    """

    def __init__(
        self,
        providers: dict[str, InferenceProvider],
        org_config: object | None = None,
        *,
        budget_gate: Any | None = None,
        grant_guard: _grants.GrantGuard | None = None,
    ) -> None:
        self._providers = providers
        self._org_config = org_config
        # Provider credit-grant guard (madfam_inference.grants). None ⇒ the
        # process-wide guard built from env; it is inert (``enabled`` False)
        # unless a grant is declared or PROVIDER_GRANTS_REQUIRED_FOR is set.
        self._grant_guard = grant_guard
        # Budget gate is opt-in: a caller can pass an instance, or the
        # router builds one on the first ``complete()`` call when the
        # ``BUDGET_GATE_ENABLED`` env flag is set and the package is
        # importable.  Once built (or determined missing) the result is
        # memoised on the instance.
        self._budget_gate: Any | None = budget_gate
        self._budget_gate_resolved: bool = budget_gate is not None

    @property
    def available_providers(self) -> list[str]:
        return list(self._providers.keys())

    def _org_override(self, policy: RoutingPolicy) -> Any | None:
        """Return the org-config ``org_overrides`` entry for the request's org.

        ``None`` for every org without an entry, so their routing is exactly
        the global routing.
        """
        if self._org_config is None or not policy.org_id:
            return None
        override_for = getattr(self._org_config, "override_for", None)
        return override_for(policy.org_id) if callable(override_for) else None

    def _priority_lists(self, policy: RoutingPolicy | None = None) -> tuple[list[str], list[str]]:
        """Return ``(cloud_priority, cheapest_priority)`` honouring org config."""
        cloud_priority = list(CLOUD_PRIORITY)
        cheapest_priority = list(CHEAPEST_PRIORITY)
        if self._org_config is not None:
            org_cloud = getattr(self._org_config, "cloud_priority", None)
            org_cheap = getattr(self._org_config, "cheapest_priority", None)
            if org_cloud:
                cloud_priority = list(org_cloud)
            if org_cheap:
                cheapest_priority = list(org_cheap)
        override = self._org_override(policy) if policy is not None else None
        if override is not None:
            if override.cloud_priority:
                cloud_priority = list(override.cloud_priority)
            if override.cheapest_priority:
                cheapest_priority = list(override.cheapest_priority)
        return cloud_priority, cheapest_priority

    def allowed_providers_for(self, request: InferenceRequest) -> list[str]:
        """Return the provider names this request's SENSITIVITY permits.

        This is the security boundary of the router and it is computed
        before any other routing input is consulted. ``restricted`` and
        ``confidential`` may only ever resolve to ``LOCAL_PROVIDER`` —
        no task-type assignment, no ``prefer_local``, no fallback chain,
        and no org-config priority list can widen this set.
        """
        policy = request.policy

        # Hard constraint: caller demanded local.
        if policy.require_local:
            return [LOCAL_PROVIDER]

        if policy.sensitivity in LOCAL_ONLY_SENSITIVITIES:
            # Regulated data (clinical notes on minors, CFDI, payroll):
            # local model only, data never leaves the perimeter.
            return [LOCAL_PROVIDER]

        if policy.provider_allowlist is not None:
            # A tenant task exception (set server-side by the gateway, see
            # tenant_policy.TaskException). The set is the allowlist
            # INTERSECTED with the router's canonical ``internal`` set, in
            # the allowlist's order. Deliberately NOT the org-config
            # ``cloud_priority`` (a cost-preference list that production
            # pins to one vendor) and never the local provider: the
            # exception names exactly where the data may go, and nothing —
            # prefer_local, a priority list, a client-sent model — adds to it.
            return [
                name for name in dict.fromkeys(policy.provider_allowlist) if name in CLOUD_PRIORITY
            ]

        cloud_priority, cheapest_priority = self._priority_lists(policy)
        if policy.sensitivity == Sensitivity.INTERNAL:
            candidates = list(cloud_priority)
        else:
            # PUBLIC -> cheapest first
            candidates = list(cheapest_priority)

        # prefer_local reorders WITHIN the allowed set; for public/internal
        # the local provider is an acceptable (and cheapest) destination.
        if policy.prefer_local:
            if LOCAL_PROVIDER in candidates:
                candidates.remove(LOCAL_PROVIDER)
            candidates.insert(0, LOCAL_PROVIDER)

        return candidates

    @staticmethod
    def _is_narrowed(policy: RoutingPolicy) -> bool:
        """True when a server-set ``provider_allowlist`` governs this request.

        Mirrors the precedence in :meth:`allowed_providers_for`: the local-only
        rules come first, so an allowlist on a restricted/confidential or
        ``require_local`` request is inert.
        """
        return (
            policy.provider_allowlist is not None
            and not policy.require_local
            and policy.sensitivity not in LOCAL_ONLY_SENSITIVITIES
        )

    def _pin_model(self, policy: RoutingPolicy, provider_name: str) -> None:
        """Pin the exception's model for ``provider_name`` before calling it.

        Done per attempt: ``model_override`` is one field shared by the
        whole request, so without this the fallback provider would be sent
        the primary's model id (or a client-chosen one). Outside an
        allowlist this is a no-op and routing behaves exactly as before.
        """
        if self._is_narrowed(policy):
            policy.model_override = policy.provider_models.get(provider_name)
            return
        # Org override fallback: when an org-override assignment points at
        # provider A but this attempt goes to provider B (A failed, or is
        # unregistered / unavailable for this call), send B the GLOBAL
        # assignment's model and limits for the task type — never A's model
        # id. Orgs without an override never reach past this check.
        override_assignment = self._override_assignment(policy)
        if override_assignment is None or override_assignment.provider == provider_name:
            return
        base = self._global_assignment(policy)
        if base is not None and base.provider == provider_name:
            policy.model_override = base.model
            if base.max_tokens:
                policy.max_tokens = base.max_tokens
            if base.temperature is not None:
                policy.temperature = base.temperature
        else:
            policy.model_override = None

    @staticmethod
    def _task_enum(policy: RoutingPolicy) -> Any | None:
        if not policy.task_type:
            return None
        from .org_config import TaskType

        try:
            return TaskType(policy.task_type)
        except ValueError:
            # Unknown task type — default routing applies.
            return None

    def _global_assignment(self, policy: RoutingPolicy) -> Any | None:
        """The org-config ``model_assignments`` entry (ignores org overrides)."""
        task_enum = self._task_enum(policy)
        if task_enum is None or self._org_config is None:
            return None
        assignments = getattr(self._org_config, "model_assignments", {})
        return assignments.get(task_enum)

    def _override_assignment(self, policy: RoutingPolicy) -> Any | None:
        """The request org's ``org_overrides`` assignment for the task type."""
        override = self._org_override(policy)
        task_enum = self._task_enum(policy)
        if override is None or task_enum is None:
            return None
        return override.model_assignments.get(task_enum)

    def _task_type_assignment(self, request: InferenceRequest) -> Any | None:
        """Return the org-config ``ModelAssignment`` for the request, if any.

        The request org's override wins for the task types it lists; every
        other case is the global assignment.
        """
        policy = request.policy
        return self._override_assignment(policy) or self._global_assignment(policy)

    def _select_provider(
        self, request: InferenceRequest, exclude: dict[str, str] | None = None
    ) -> InferenceProvider:
        """Determine which provider to use for the given request.

        Order is load-bearing: the sensitivity-allowed set is computed
        FIRST, and every later decision picks inside it. ``exclude`` (provider
        name -> reason) holds grant-guarded providers that are unavailable
        for this call; it can only remove candidates, never add one.
        """
        policy = request.policy
        exclude = exclude or {}

        # ── 1. Sensitivity gate (never overridable) ───────────────────
        candidates = self.allowed_providers_for(request)
        if exclude:
            candidates = [n for n in candidates if n not in exclude]

        # ── 2. Task-type routing, constrained to the allowed set ──────
        # Under a tenant task exception the org-config model_assignments
        # are not consulted at all: the exception pins providers, order and
        # models, so an assignment can neither widen the set nor swap the
        # model or raise the token cap.
        assignment = None if self._is_narrowed(policy) else self._task_type_assignment(request)
        if assignment is not None and assignment.provider in exclude:
            logger.info(
                "Task-type routing: %s is assigned to grant-guarded provider %s, "
                "unavailable for this call (%s); using the next allowed provider.",
                policy.task_type,
                assignment.provider,
                exclude[assignment.provider],
            )
        elif assignment is not None:
            if assignment.provider not in candidates:
                # THE bypass this guard exists to close: an org-config
                # model_assignments entry must never be able to send
                # restricted/confidential data to a cloud vendor.
                logger.warning(
                    "Task-type routing REFUSED: task_type=%s is assigned to "
                    "provider %s, which is not permitted for sensitivity=%s "
                    "(allowed: %s). Falling back to sensitivity routing.",
                    policy.task_type,
                    assignment.provider,
                    policy.sensitivity.value,
                    candidates,
                )
            else:
                provider = self._providers.get(assignment.provider)
                if provider is not None:
                    policy.model_override = assignment.model
                    if assignment.max_tokens:
                        policy.max_tokens = assignment.max_tokens
                    if assignment.temperature is not None:
                        policy.temperature = assignment.temperature
                    logger.debug(
                        "Task-type routing: %s → %s/%s",
                        policy.task_type,
                        assignment.provider,
                        assignment.model,
                    )
                    return provider
                logger.debug(
                    "Task-type assignment for %s points to %s, "
                    "but provider is not registered — falling through",
                    policy.task_type,
                    assignment.provider,
                )

        # ── 3. First registered provider inside the allowed set ───────
        if policy.require_local and self._providers.get(LOCAL_PROVIDER) is None:
            raise RuntimeError("require_local is True but no Ollama provider is registered.")

        # For multimodal requests, prefer vision-capable providers — still
        # only ever WITHIN the sensitivity-allowed set.
        if request.has_media():
            vision_candidates = [
                n
                for n in candidates
                if self._providers.get(n) and self._providers[n].supports_vision
            ]
            if vision_candidates:
                candidates = vision_candidates

        for name in candidates:
            provider = self._providers.get(name)
            if provider is not None:
                self._pin_model(policy, name)
                return provider

        grant_note = (
            " Grant-guarded and unavailable: "
            + ", ".join(f"{n} ({r})" for n, r in exclude.items())
            + "."
            if exclude
            else ""
        )
        raise RuntimeError(
            f"No available provider for sensitivity={policy.sensitivity.value}. "
            f"Tried: {candidates}. Registered: {self.available_providers}.{grant_note}"
        )

    # ── Provider credit grants (madfam_inference.grants) ──────────────

    def _active_grant_guard(self) -> _grants.GrantGuard | None:
        guard = self._grant_guard or _grants.get_default_guard()
        return guard if guard.enabled else None

    def _provider_name(self, provider: InferenceProvider) -> str:
        for name, registered in self._providers.items():
            if registered is provider:
                return name
        return getattr(provider, "name", type(provider).__name__.lower())

    async def _select_provider_guarded(
        self, request: InferenceRequest
    ) -> tuple[InferenceProvider, _grants.Reservation | None, dict[str, str]]:
        """``_select_provider`` plus the grant guard.

        When the chosen provider is grant-guarded, reserve the call's worst
        case on its grant. On denial the provider is excluded and selection
        re-runs from the caller's original policy (so an org assignment's
        model never leaks to the next provider). A model the CALLER pinned
        that would have gone to the denied provider raises
        ``ProviderGrantUnavailableError`` instead of being silently swapped.
        """
        guard = self._active_grant_guard()
        if guard is None:
            return self._select_provider(request), None, {}
        policy = request.policy
        original = policy.model_copy(deep=True)
        excluded: dict[str, str] = {}
        while True:
            provider = self._select_provider(request, excluded)
            name = self._provider_name(provider)
            decision = await guard.reserve(name, policy.org_id, policy.model_override, request)
            if decision.allowed:
                return provider, decision.reservation, excluded
            caller_model = original.model_override
            if (
                caller_model
                and policy.model_override == caller_model
                and _grants.is_pinned_to(name, caller_model)
            ):
                raise _grants.ProviderGrantUnavailableError(
                    f"Model {caller_model!r} runs on provider {name!r}, which is "
                    f"grant-guarded and unavailable for this call ({decision.reason}). "
                    "The pinned model is not swapped for another provider's."
                )
            excluded[name] = decision.reason
            for field_name in type(policy).model_fields:
                setattr(policy, field_name, getattr(original, field_name))

    async def _call_complete(
        self,
        provider: InferenceProvider,
        request: InferenceRequest,
        reservation: _grants.Reservation | None,
    ) -> InferenceResponse:
        """``provider.complete`` with grant settle (success) / release (error)."""
        if reservation is None:
            return await provider.complete(request)
        try:
            response = await provider.complete(request)
        except asyncio.CancelledError:
            # A timed-out call may still be billed upstream: count the worst case.
            reservation.guard.settle_in_background(reservation)
            raise
        except BaseException:
            await reservation.release()
            raise
        await reservation.settle(response.model, response.usage)
        return response

    async def _reserve_attempt(
        self, name: str, request: InferenceRequest, excluded: dict[str, str]
    ) -> tuple[bool, _grants.Reservation | None]:
        """Reserve for a retry / fallback attempt. ``(False, None)`` ⇒ skip ``name``."""
        if name in excluded:
            return False, None
        guard = self._active_grant_guard()
        if guard is None:
            return True, None
        decision = await guard.reserve(
            name, request.policy.org_id, request.policy.model_override, request
        )
        if not decision.allowed:
            excluded[name] = decision.reason
            logger.info("Skipping grant-guarded provider %s: %s", name, decision.reason)
            return False, None
        return True, decision.reservation

    def _get_fallback_candidates(
        self,
        request: InferenceRequest,
        exclude: InferenceProvider,
    ) -> list[str]:
        """Return provider names suitable for fallback, excluding the primary.

        Fallback is drawn from the SAME sensitivity-allowed set as primary
        selection, so a restricted/confidential request can never fall back
        to a cloud vendor — for those levels the only allowed provider is
        the primary, so the list is empty by construction. Under a
        ``provider_allowlist`` the chain is the rest of the allowlist, in
        order, and nothing else.
        """
        policy = request.policy
        if policy.sensitivity in LOCAL_ONLY_SENSITIVITIES or policy.require_local:
            return []  # Cannot fall back from the local-only constraint

        return [
            n
            for n in self.allowed_providers_for(request)
            if self._providers.get(n) is not None and self._providers[n] is not exclude
        ]

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        """Route the request to the appropriate provider and return the response.

        Retries once on the primary provider (with 1s delay), then falls
        through to alternative providers before raising.

        When ``BUDGET_GATE_ENABLED=true`` and the ``madfam-budget-gate``
        package is importable, every call is gated by an org/agent/global
        spend check before dispatch.  After a successful response the
        actual usage is recorded against the same scope so daily and
        monthly caps stay accurate.  Default OFF — operators flip the
        flag in production after the first smoke pass.
        """
        gate, scope = await self._check_budget_preflight(request)

        response = await self._complete_inner(request)

        # Post-call recording — fire-and-forget: a record() failure must
        # never break the inference path.  The gate's own record() logs
        # exceptions internally, but we add an extra try/except for the
        # local import path.
        if gate is not None and scope is not None:
            try:
                usage = response.usage or {}
                input_tokens = int(usage.get("input_tokens", 0))
                output_tokens = int(usage.get("output_tokens", 0))
                await gate.record(
                    scope,
                    actual_tokens=input_tokens + output_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    provider=response.provider,
                    model=response.model,
                    **_cache_cost_kwargs(
                        response.provider,
                        response.model,
                        input_tokens,
                        output_tokens,
                        int(usage.get("cache_read_input_tokens", 0)),
                        int(usage.get("cache_creation_input_tokens", 0)),
                    ),
                )
            except Exception as exc:
                logger.warning("budget-gate: record() raised: %s", exc)

        return response

    async def _check_budget_preflight(self, request: InferenceRequest) -> tuple[Any, Any]:
        """Run the opt-in budget gate before a provider call."""
        gate, scope = self._resolve_gate_and_scope(request)
        if gate is not None and scope is not None:
            decision = await gate.check(
                scope,
                estimated_tokens=request.policy.max_tokens,
                estimated_cost_usd=0.0,
            )
            if not decision.allowed:
                from madfam_budget_gate import BudgetExhausted  # local import

                raise BudgetExhausted(decision.reason, decision.retry_after_seconds)
        return gate, scope

    def _apply_prompt_cache_breakpoints(
        self,
        request: InferenceRequest,
        provider: InferenceProvider,
    ) -> None:
        provider_name = type(provider).__name__.lower().replace("provider", "")
        new_messages, _system_with_cache = _cache_manager.apply_cache_breakpoints(
            request.messages,
            system_prompt=request.system_prompt or "",
            provider=provider_name,
        )
        request.messages = new_messages

    async def _complete_inner(self, request: InferenceRequest) -> InferenceResponse:
        provider, reservation, excluded = await self._select_provider_guarded(request)
        provider_name = self._provider_name(provider)

        # Gap 7: prompt caching. The system prompt stays a raw string on the
        # request (so a fallback to another vendor gets plain text); the
        # Anthropic adapter turns it into a ``cache_control: ephemeral``
        # content block when it builds the request body (``_build_body``),
        # which is what actually reaches the API.
        self._apply_prompt_cache_breakpoints(request, provider)

        # Try primary provider with 1 retry — but only retry when the
        # failure is fallback-eligible. Hard-failures (401/422/etc.) are
        # surfaced immediately so ops sees the real cause.
        last_exc: Exception | None = None
        for attempt in range(2):
            if attempt > 0 and reservation is None:
                ok, reservation = await self._reserve_attempt(provider_name, request, excluded)
                if not ok:
                    break
            try:
                return await self._call_complete(provider, request, reservation)
            except Exception as exc:
                reservation = None
                last_exc = exc
                eligible = _is_fallback_eligible(exc)
                logger.warning(
                    "Provider %s failed (attempt %d/2, fallback_eligible=%s): %s",
                    type(provider).__name__,
                    attempt + 1,
                    eligible,
                    exc,
                )
                if not eligible:
                    # Auth / 404 / 422: re-raise immediately. No retry,
                    # no fallback — the same request will fail the same
                    # way on the next provider too.
                    raise
                if attempt == 0:
                    await asyncio.sleep(1.0)

        # Fallback: try remaining candidates. We only get here if the
        # primary's failure was fallback-eligible (otherwise we re-raised
        # above), so unconditional fall-through is correct.
        for name in self._get_fallback_candidates(request, exclude=provider):
            ok, fb_reservation = await self._reserve_attempt(name, request, excluded)
            if not ok:
                continue
            try:
                logger.info("Falling back to provider: %s", name)
                self._pin_model(request.policy, name)
                return await self._call_complete(self._providers[name], request, fb_reservation)
            except Exception as exc:
                # Fallback chain: only stop early on a hard-failure
                # (e.g. 401 from a misconfigured fallback key) AND log
                # so the operator knows the chain dead-ended.
                logger.warning(
                    "Fallback provider %s also failed (fallback_eligible=%s): %s",
                    name,
                    _is_fallback_eligible(exc),
                    exc,
                )
                last_exc = exc

        raise RuntimeError(f"All providers failed for request. Last error: {last_exc}")

    def _resolve_gate_and_scope(self, request: InferenceRequest) -> tuple[Any, Any]:
        """Return ``(gate, scope)`` if budget gate is enabled, else ``(None, None)``.

        First call lazily resolves the gate; subsequent calls reuse the
        cached value.  Scope is built from request metadata: in this
        bootstrap integration we honour the ``BUDGET_GATE_DEFAULT_ORG_ID``
        env var as the org_id and leave agent_id unset.  Callers that
        need finer-grained scoping should pass an explicit gate
        instance via the constructor.
        """
        if not _budget_gate_enabled():
            return None, None
        if not self._budget_gate_resolved:
            self._budget_gate_resolved = True
            module = _try_import_budget_gate()
            if module is None:
                self._budget_gate = None
            else:
                try:
                    self._budget_gate = module.BudgetGate.from_env()
                except Exception as exc:
                    logger.warning("budget-gate: from_env() failed: %s", exc)
                    self._budget_gate = None
        if self._budget_gate is None:
            return None, None

        # Scope extraction — minimal and overridable.  Callers wanting
        # per-agent scoping inject a gate via constructor + a custom
        # extraction strategy upstream.
        from madfam_budget_gate import BudgetScope  # local import

        org_id = os.environ.get("BUDGET_GATE_DEFAULT_ORG_ID") or None
        scope = BudgetScope(org_id=org_id)
        return self._budget_gate, scope

    async def stream(
        self,
        request: InferenceRequest,
        on_usage: UsageCallback | None = None,
    ) -> AsyncIterator[str]:
        """Route the request and stream the response.

        Streaming applies the same budget preflight, prompt-cache preparation,
        and provider fallback classification as ``complete()``. It only falls
        back before any chunk is emitted; once a provider has started streaming,
        switching vendors would splice two model responses into one output.

        Providers report final token accounting through ``on_usage`` (at most
        once, at stream end). The router stamps the winning provider's name,
        records the spend against the budget gate — mirroring ``complete()``'s
        post-call recording — and forwards the usage to the caller so streamed
        inference is billed like non-streamed inference.
        """
        gate, scope = await self._check_budget_preflight(request)
        provider, reservation, excluded = await self._select_provider_guarded(request)
        self._apply_prompt_cache_breakpoints(request, provider)

        captured: list[StreamUsage] = []

        async def _finish_grant(res: _grants.Reservation | None, *, emitted: bool) -> None:
            # Settle on actual usage; a stream that emitted but reported no
            # usage (or broke mid-way) settles the worst case. Nothing
            # emitted and failed ⇒ release.
            if res is None:
                return
            if captured:
                last = captured[-1]
                await res.settle(
                    last.model or request.policy.model_override,
                    {"input_tokens": last.input_tokens, "output_tokens": last.output_tokens},
                )
            elif emitted:
                await res.settle_worst_case()
            else:
                await res.release()

        def _make_capture(provider_name: str) -> UsageCallback:
            def _capture(usage: StreamUsage) -> None:
                usage.provider = provider_name
                captured.append(usage)
                if on_usage is not None:
                    on_usage(usage)

            return _capture

        async def _record_captured() -> None:
            # Same fire-and-forget posture as complete(): a record() failure
            # must never break the inference path.
            if gate is None or scope is None or not captured:
                return
            usage = captured[-1]
            try:
                await gate.record(
                    scope,
                    actual_tokens=usage.input_tokens + usage.output_tokens,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    provider=usage.provider,
                    model=usage.model,
                    **_cache_cost_kwargs(
                        usage.provider,
                        usage.model,
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.cache_read_input_tokens,
                        usage.cache_creation_input_tokens,
                    ),
                )
            except Exception as exc:
                logger.warning("budget-gate: record() raised for stream: %s", exc)

        emitted_any = False
        last_exc: Exception | None = None
        try:
            async for chunk in provider.stream(
                request, on_usage=_make_capture(provider.name)
            ):
                emitted_any = True
                yield chunk
            await _finish_grant(reservation, emitted=True)
            await _record_captured()
            return
        except asyncio.CancelledError:
            if reservation is not None:
                reservation.guard.settle_in_background(reservation)
            raise
        except Exception as exc:
            await _finish_grant(reservation, emitted=emitted_any)
            last_exc = exc
            eligible = _is_fallback_eligible(exc)
            logger.warning(
                "Streaming provider %s failed (emitted_any=%s, fallback_eligible=%s): %s",
                type(provider).__name__,
                emitted_any,
                eligible,
                exc,
            )
            if emitted_any or not eligible:
                raise

        for name in self._get_fallback_candidates(request, exclude=provider):
            fallback = self._providers[name]
            emitted_any = False
            ok, fb_reservation = await self._reserve_attempt(name, request, excluded)
            if not ok:
                continue
            self._pin_model(request.policy, name)
            try:
                logger.info("Falling back streaming inference to provider: %s", name)
                async for chunk in fallback.stream(
                    request, on_usage=_make_capture(fallback.name)
                ):
                    emitted_any = True
                    yield chunk
                await _finish_grant(fb_reservation, emitted=True)
                await _record_captured()
                return
            except asyncio.CancelledError:
                if fb_reservation is not None:
                    fb_reservation.guard.settle_in_background(fb_reservation)
                raise
            except Exception as exc:
                await _finish_grant(fb_reservation, emitted=emitted_any)
                last_exc = exc
                logger.warning(
                    "Streaming fallback provider %s failed "
                    "(emitted_any=%s, fallback_eligible=%s): %s",
                    name,
                    emitted_any,
                    _is_fallback_eligible(exc),
                    exc,
                )
                if emitted_any:
                    raise

        raise RuntimeError(f"All streaming providers failed for request. Last error: {last_exc}")
