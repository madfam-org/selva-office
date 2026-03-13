import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const e2eDuration = new Trend("e2e_approval_duration_ms");

const BASE_URL = __ENV.BASE_URL || "http://localhost:4300";
const TOKEN = __ENV.AUTH_TOKEN || "dev-token";

export const options = {
  stages: [
    { duration: "30s", target: 5 },
    { duration: "1m", target: 10 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    e2e_approval_duration_ms: ["p(95)<5000"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

export default function () {
  const start = Date.now();

  // 1. Dispatch a task
  const dispatchRes = http.post(
    `${BASE_URL}/api/v1/swarms/dispatch`,
    JSON.stringify({
      description: `E2E approval test ${Date.now()}`,
      graph_type: "coding",
    }),
    { headers }
  );

  if (dispatchRes.status !== 201) {
    return;
  }

  const taskId = JSON.parse(dispatchRes.body).id;

  // 2. Wait briefly for worker to pick up and create approval
  sleep(1);

  // 3. List pending approvals
  const approvalsRes = http.get(`${BASE_URL}/api/v1/approvals/`, { headers });
  check(approvalsRes, {
    "approvals listed": (r) => r.status === 200,
  });

  if (approvalsRes.status === 200) {
    const approvals = JSON.parse(approvalsRes.body);
    if (approvals.length > 0) {
      // 4. Approve the first pending request
      const approvalId = approvals[0].id;
      const approveRes = http.post(
        `${BASE_URL}/api/v1/approvals/${approvalId}/approve`,
        JSON.stringify({ feedback: "Auto-approved by load test" }),
        { headers }
      );
      check(approveRes, {
        "approval succeeded": (r) => r.status === 200,
      });
    }
  }

  e2eDuration.add(Date.now() - start);
  sleep(2);
}
