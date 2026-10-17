#!/usr/bin/env python3
"""Bootstrap MADFAM's factory-line departments and agents in Selva.

Reads ``data/factory-lines/madfam-factory-lines.yaml`` and, for MADFAM's own
tenant (the platform org, ``PLATFORM_ORG_ID``, default ``madfam``), creates
any missing department (matched by slug) and agent (matched by name) through
the Nexus API. Same pattern as ``scripts/seed-madfam-org.py``.

Idempotent and create-if-missing only: it never updates, moves or deletes an
existing department or agent, so re-running it is safe. A slug that already
exists outside the org (department slugs are globally unique) is reported as
a conflict and skipped — never silently reused.

Usage (platform admin, against the target environment):

  SELVA_API_URL=<nexus-api base URL> SELVA_TOKEN=<platform-admin token> \
    python scripts/seed-madfam-factory-lines.py [--org-id madfam]
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROSTER_PATH = Path(__file__).resolve().parents[1] / "data" / "factory-lines" / (
    "madfam-factory-lines.yaml"
)
VALID_ROLES = {"planner", "coder", "reviewer", "researcher", "crm", "support"}


@dataclass
class RosterPlan:
    """What the bootstrap would create, given the org's current state."""

    departments_to_create: list[dict[str, Any]] = field(default_factory=list)
    agents_to_create: list[dict[str, Any]] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def load_roster(path: Path = ROSTER_PATH) -> dict[str, Any]:
    """Load and validate the factory-lines roster file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "selva.factory-lines/v1":
        raise ValueError(f"{path}: expected schema selva.factory-lines/v1")
    lines = data.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError(f"{path}: 'lines' must be a non-empty list")
    slugs: set[str] = set()
    names: set[str] = set()
    for line in lines:
        dept = line.get("department") or {}
        slug = dept.get("slug")
        if not slug or slug in slugs:
            raise ValueError(f"{path}: line {line.get('id')!r} has a missing/duplicate slug")
        slugs.add(slug)
        for agent in line.get("agents") or []:
            if agent.get("role") not in VALID_ROLES:
                raise ValueError(f"{path}: agent {agent.get('name')!r} has invalid role")
            if agent["name"] in names:
                raise ValueError(f"{path}: duplicate agent name {agent['name']!r}")
            names.add(agent["name"])
    return data


def plan_roster(
    roster: dict[str, Any],
    org_departments: list[dict[str, Any]],
    org_agents: list[dict[str, Any]],
    global_slugs: set[str] | None = None,
) -> RosterPlan:
    """Compute the create-if-missing plan for the org.

    ``org_departments`` / ``org_agents`` are the org's current rows (as the
    tenant-scoped list endpoints return them). ``global_slugs`` are slugs
    known to exist in *other* orgs; a roster slug found there is a conflict.
    """
    plan = RosterPlan()
    org_slugs = {d["slug"] for d in org_departments}
    agent_names = {a["name"] for a in org_agents}
    global_slugs = global_slugs or set()

    for line in roster["lines"]:
        dept = line["department"]
        slug = dept["slug"]
        if slug in org_slugs:
            plan.existing.append(f"department:{slug}")
        elif slug in global_slugs:
            plan.conflicts.append(f"department:{slug} exists in another org")
            continue
        else:
            plan.departments_to_create.append(
                {
                    "name": dept["name"],
                    "slug": slug,
                    "description": " ".join(str(dept.get("description", "")).split()),
                    "max_agents": int(dept.get("max_agents", 5)),
                    "position_x": int(dept.get("position_x", 0)),
                    "position_y": int(dept.get("position_y", 0)),
                }
            )
        for agent in line.get("agents") or []:
            if agent["name"] in agent_names:
                plan.existing.append(f"agent:{agent['name']}")
                continue
            plan.agents_to_create.append(
                {
                    "name": agent["name"],
                    "role": agent["role"],
                    "level": int(agent.get("level", 1)),
                    "skill_ids": list(agent.get("skill_ids") or []),
                    "department_slug": slug,
                }
            )
    return plan


def _items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        items = response.get("items", [])
        return items if isinstance(items, list) else []
    return response if isinstance(response, list) else []


def main() -> int:
    import httpx

    parser = argparse.ArgumentParser(description="Bootstrap MADFAM factory lines")
    parser.add_argument("--api-url", default=os.environ.get("SELVA_API_URL", ""))
    parser.add_argument("--token", default=os.environ.get("SELVA_TOKEN", ""))
    parser.add_argument(
        "--org-id",
        default=os.environ.get("SELVA_ORG_ID") or os.environ.get("PLATFORM_ORG_ID") or "madfam",
    )
    args = parser.parse_args()
    if not args.api_url or not args.token:
        print("✗  SELVA_API_URL and SELVA_TOKEN (or --api-url/--token) are required")
        return 2

    headers = {
        "Authorization": f"Bearer {args.token}",
        "Content-Type": "application/json",
        "X-Selva-Tenant-Org": args.org_id,
    }
    base = args.api_url.rstrip("/")
    client = httpx.Client(headers=headers, timeout=15)

    def get(path: str) -> Any:
        r = client.get(f"{base}{path}")
        r.raise_for_status()
        return r.json()

    roster = load_roster()
    departments = _items(get("/api/v1/departments/?limit=200"))
    agents = _items(get("/api/v1/agents/?limit=200"))
    plan = plan_roster(roster, departments, agents)

    print(f"Org {args.org_id}: {len(plan.existing)} already present")
    slug_to_id = {d["slug"]: d["id"] for d in departments}
    failures = 0
    for dept in plan.departments_to_create:
        r = client.post(f"{base}/api/v1/departments/", json=dept)
        if r.status_code == 409:
            print(f"  !  department {dept['slug']}: slug taken (conflict) — skipped")
            plan.conflicts.append(f"department:{dept['slug']}")
            continue
        if r.status_code not in (200, 201):
            print(f"  ✗  department {dept['slug']}: HTTP {r.status_code}")
            failures += 1
            continue
        slug_to_id[dept["slug"]] = r.json()["id"]
        print(f"  ✚  department {dept['slug']}")

    for agent in plan.agents_to_create:
        dept_id = slug_to_id.get(agent["department_slug"])
        if not dept_id:
            print(f"  ✗  agent {agent['name']}: department {agent['department_slug']} missing")
            failures += 1
            continue
        body = {k: v for k, v in agent.items() if k != "department_slug"}
        body["department_id"] = dept_id
        r = client.post(f"{base}/api/v1/agents/", json=body)
        if r.status_code not in (200, 201):
            print(f"  ✗  agent {agent['name']}: HTTP {r.status_code}")
            failures += 1
            continue
        print(f"  ✚  agent {agent['name']} [{agent['role']}] → {agent['department_slug']}")

    for conflict in plan.conflicts:
        print(f"  !  conflict: {conflict}")
    if failures or plan.conflicts:
        print(f"✗  finished with {failures} failure(s), {len(plan.conflicts)} conflict(s)")
        return 1
    print("✓  factory lines present for the org")
    return 0


if __name__ == "__main__":
    sys.exit(main())
