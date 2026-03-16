import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  OfficeStateSchema,
  DepartmentSchema,
} from "../schema/OfficeState";
import { DemoSimulator } from "../demo/DemoSimulator";

function createStateWithDepartments(): OfficeStateSchema {
  const state = new OfficeStateSchema();

  const depts = [
    { id: "dept-engineering", name: "Engineering", slug: "engineering", maxAgents: 6, x: 100, y: 100 },
    { id: "dept-research", name: "Research", slug: "research", maxAgents: 4, x: 600, y: 100 },
    { id: "dept-crm", name: "CRM", slug: "crm", maxAgents: 4, x: 100, y: 400 },
    { id: "dept-support", name: "Support", slug: "support", maxAgents: 4, x: 600, y: 400 },
  ];

  for (const d of depts) {
    const dept = new DepartmentSchema();
    dept.id = d.id;
    dept.name = d.name;
    dept.slug = d.slug;
    dept.maxAgents = d.maxAgents;
    dept.x = d.x;
    dept.y = d.y;
    state.departments.set(d.id, dept);
  }

  return state;
}

describe("DemoSimulator", () => {
  let state: OfficeStateSchema;
  let simulator: DemoSimulator;

  beforeEach(() => {
    vi.useFakeTimers();
    state = createStateWithDepartments();
    simulator = new DemoSimulator(state);
  });

  afterEach(() => {
    simulator.stop();
    vi.useRealTimers();
  });

  it("populates 8 demo agents on start", () => {
    simulator.start();

    let totalAgents = 0;
    state.departments.forEach((dept) => {
      totalAgents += dept.agents.length;
    });

    expect(totalAgents).toBe(8);
  });

  it("distributes agents across departments", () => {
    simulator.start();

    const eng = state.departments.get("dept-engineering");
    const research = state.departments.get("dept-research");
    const crm = state.departments.get("dept-crm");
    const support = state.departments.get("dept-support");

    expect(eng?.agents.length).toBe(3);
    expect(research?.agents.length).toBe(2);
    expect(crm?.agents.length).toBe(1);
    expect(support?.agents.length).toBe(2);
  });

  it("agents start as idle", () => {
    simulator.start();

    state.departments.forEach((dept) => {
      for (let i = 0; i < dept.agents.length; i++) {
        const agent = dept.agents.at(i);
        expect(agent?.status).toBe("idle");
      }
    });
  });

  it("generates system messages when tasks start", () => {
    simulator.start();

    // Advance past the initial task timer (3s) plus some buffer
    vi.advanceTimersByTime(4000);

    // At least one task should have started, generating a chat message
    expect(state.chatMessages.length).toBeGreaterThan(0);
  });

  it("resolveApproval changes agent status to idle", () => {
    simulator.start();

    // Manually set an agent to waiting_approval
    const eng = state.departments.get("dept-engineering");
    const agent = eng?.agents.at(0);
    if (agent) {
      agent.status = "waiting_approval";
      state.pendingApprovalCount = 1;

      const resolved = simulator.resolveApproval(agent.id, "approved");
      expect(resolved).toBe(true);
      expect(agent.status).toBe("idle");
      expect(state.pendingApprovalCount).toBe(0);
    }
  });

  it("resolveApproval returns false for unknown agent", () => {
    simulator.start();
    const resolved = simulator.resolveApproval("nonexistent", "approved");
    expect(resolved).toBe(false);
  });

  it("stop clears all timers", () => {
    simulator.start();
    // Should not throw
    simulator.stop();
    // Advance timers — nothing should happen
    vi.advanceTimersByTime(60_000);
  });
});
