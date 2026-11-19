"""Selva A2A -- Agent-to-Agent protocol implementation.

Two surfaces coexist:

- **Legacy 0.7.0 dialect** (:mod:`selva_a2a.server` / :mod:`selva_a2a.schema` /
  :mod:`selva_a2a.client`): card at ``/.well-known/agent.json``, REST-ish
  ``tasks/send`` / ``tasks/get`` / ``tasks/sendSubscribe``. Unchanged; existing
  consumers keep using it.
- **v1.0.1-compatible surface** (:mod:`selva_a2a.v1`): card at
  ``/.well-known/agent-card.json``, JSON-RPC 2.0 (``message/send``,
  ``message/stream``, ``tasks/get``, ``tasks/cancel``), SCREAMING_SNAKE task
  states. Additive and inert unless mounted behind a feature gate. An optional
  task announcer (:mod:`selva_a2a.announce`) POSTs newly-created tasks to a
  configurable observability intake.
"""

from .announce import (
    announce_task,
    build_announcement,
    is_announcer_enabled,
    schedule_announcement,
)
from .client import A2AClient
from .schema import AgentCard, AgentSkill, TaskRequest, TaskResponse, TaskStatus
from .server import create_a2a_router
from .v1 import (
    A2A_V1_AGENT_CARD_PATH,
    A2A_V1_PROTOCOL_VERSION,
    AgentCapabilities,
    AgentCardV1,
    AgentInterface,
    MessageSendParams,
    TaskSnapshotV1,
    TaskState,
    TaskStatusV1,
    create_a2a_v1_router,
    selva_status_to_task_state,
)

__all__ = [
    # -- legacy 0.7.0 surface --
    "A2AClient",
    "AgentCard",
    "AgentSkill",
    "TaskRequest",
    "TaskResponse",
    "TaskStatus",
    "create_a2a_router",
    # -- v1.0.1 surface --
    "A2A_V1_AGENT_CARD_PATH",
    "A2A_V1_PROTOCOL_VERSION",
    "AgentCapabilities",
    "AgentCardV1",
    "AgentInterface",
    "MessageSendParams",
    "TaskSnapshotV1",
    "TaskState",
    "TaskStatusV1",
    "create_a2a_v1_router",
    "selva_status_to_task_state",
    # -- announcer --
    "announce_task",
    "build_announcement",
    "is_announcer_enabled",
    "schedule_announcement",
]
