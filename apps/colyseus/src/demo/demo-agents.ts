/**
 * Hardcoded demo agents for the demo/sandbox environment.
 * 8 agents across 4 departments — no API calls needed.
 */

export interface DemoAgentDef {
  id: string;
  name: string;
  role: string;
  level: number;
  departmentId: string;
  skills: string[];
}

export const DEMO_AGENTS: DemoAgentDef[] = [
  // Engineering (3)
  {
    id: "demo-agent-1",
    name: "Atlas",
    role: "coder",
    level: 4,
    departmentId: "dept-engineering",
    skills: ["python", "typescript", "git-operations"],
  },
  {
    id: "demo-agent-2",
    name: "Nova",
    role: "planner",
    level: 3,
    departmentId: "dept-engineering",
    skills: ["task-decomposition", "code-review", "architecture"],
  },
  {
    id: "demo-agent-3",
    name: "Prism",
    role: "reviewer",
    level: 3,
    departmentId: "dept-engineering",
    skills: ["code-review", "testing", "security-audit"],
  },
  // Research (2)
  {
    id: "demo-agent-4",
    name: "Echo",
    role: "researcher",
    level: 3,
    departmentId: "dept-research",
    skills: ["web-search", "data-analysis", "report-writing"],
  },
  {
    id: "demo-agent-5",
    name: "Sage",
    role: "researcher",
    level: 2,
    departmentId: "dept-research",
    skills: ["web-search", "summarization", "research"],
  },
  // CRM (1)
  {
    id: "demo-agent-6",
    name: "Pulse",
    role: "crm",
    level: 2,
    departmentId: "dept-crm",
    skills: ["email-drafting", "crm-operations", "customer-support"],
  },
  // Support (2)
  {
    id: "demo-agent-7",
    name: "Shield",
    role: "support",
    level: 3,
    departmentId: "dept-support",
    skills: ["ticket-triage", "documentation", "troubleshooting"],
  },
  {
    id: "demo-agent-8",
    name: "Beacon",
    role: "support",
    level: 2,
    departmentId: "dept-support",
    skills: ["customer-support", "escalation", "knowledge-base"],
  },
];

export const DEMO_TASK_DESCRIPTIONS = [
  "Implement JWT refresh token rotation",
  "Fix dashboard layout on mobile",
  "Optimize database query for user search",
  "Add unit tests for billing module",
  "Update API documentation for v2 endpoints",
  "Research competitor feature matrix",
  "Draft quarterly product roadmap",
  "Set up CI pipeline for staging branch",
  "Fix memory leak in WebSocket handler",
  "Add rate limiting to public API",
  "Create onboarding email sequence",
  "Audit RBAC permissions for admin routes",
  "Migrate legacy CSV importer to streaming",
  "Add dark mode support to settings page",
  "Write integration tests for payment flow",
];
