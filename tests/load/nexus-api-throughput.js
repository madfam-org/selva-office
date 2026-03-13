import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("errors");
const taskDispatchDuration = new Trend("task_dispatch_duration");

const BASE_URL = __ENV.BASE_URL || "http://localhost:4300";
const TOKEN = __ENV.AUTH_TOKEN || "dev-token";

export const options = {
  stages: [
    { duration: "30s", target: 10 },
    { duration: "1m", target: 50 },
    { duration: "1m", target: 100 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],
    errors: ["rate<0.01"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

export default function () {
  // Health check
  const healthRes = http.get(`${BASE_URL}/api/v1/health/health`);
  check(healthRes, {
    "health status 200": (r) => r.status === 200,
  });

  // List tasks
  const tasksRes = http.get(`${BASE_URL}/api/v1/swarms/tasks`, { headers });
  check(tasksRes, {
    "tasks status 200": (r) => r.status === 200,
  });
  errorRate.add(tasksRes.status !== 200);

  // Dispatch a task (every ~5th iteration)
  if (Math.random() < 0.2) {
    const start = Date.now();
    const dispatchRes = http.post(
      `${BASE_URL}/api/v1/swarms/dispatch`,
      JSON.stringify({
        description: `Load test task ${Date.now()}`,
        graph_type: "research",
      }),
      { headers }
    );
    taskDispatchDuration.add(Date.now() - start);
    check(dispatchRes, {
      "dispatch status 201": (r) => r.status === 201,
    });
    errorRate.add(dispatchRes.status !== 201);
  }

  // List approvals
  const approvalsRes = http.get(`${BASE_URL}/api/v1/approvals/`, { headers });
  check(approvalsRes, {
    "approvals status 200": (r) => r.status === 200,
  });

  sleep(0.5);
}
