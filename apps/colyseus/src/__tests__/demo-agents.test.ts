import { describe, it, expect } from "vitest";
import { DEMO_AGENTS, DEMO_TASK_DESCRIPTIONS } from "../demo/demo-agents";

describe("demo-agents", () => {
  it("defines 8 demo agents", () => {
    expect(DEMO_AGENTS).toHaveLength(8);
  });

  it("each agent has required fields", () => {
    for (const agent of DEMO_AGENTS) {
      expect(agent.id).toBeTruthy();
      expect(agent.name).toBeTruthy();
      expect(agent.role).toBeTruthy();
      expect(agent.departmentId).toMatch(/^dept-/);
      expect(agent.level).toBeGreaterThan(0);
      expect(agent.skills.length).toBeGreaterThan(0);
    }
  });

  it("agent IDs are unique", () => {
    const ids = DEMO_AGENTS.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("covers all 4 departments", () => {
    const depts = new Set(DEMO_AGENTS.map((a) => a.departmentId));
    expect(depts).toContain("dept-engineering");
    expect(depts).toContain("dept-research");
    expect(depts).toContain("dept-crm");
    expect(depts).toContain("dept-support");
  });

  it("has task description pool", () => {
    expect(DEMO_TASK_DESCRIPTIONS.length).toBeGreaterThan(10);
    for (const desc of DEMO_TASK_DESCRIPTIONS) {
      expect(typeof desc).toBe("string");
      expect(desc.length).toBeGreaterThan(5);
    }
  });
});
