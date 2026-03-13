import http from "k6/http";
import { check, sleep } from "k6";
import { Gauge, Rate } from "k6/metrics";

const queueDepth = new Gauge("queue_depth");
const errorRate = new Rate("errors");

const BASE_URL = __ENV.BASE_URL || "http://localhost:4300";
const TOKEN = __ENV.AUTH_TOKEN || "dev-token";

export const options = {
  scenarios: {
    dispatch: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1m",
      duration: "3m",
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  thresholds: {
    errors: ["rate<0.01"],
    queue_depth: ["value<50"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

export default function () {
  const graphTypes = ["coding", "research", "crm"];
  const graphType = graphTypes[Math.floor(Math.random() * graphTypes.length)];

  const res = http.post(
    `${BASE_URL}/api/v1/swarms/dispatch`,
    JSON.stringify({
      description: `Queue throughput test: ${graphType} ${Date.now()}`,
      graph_type: graphType,
    }),
    { headers }
  );

  check(res, {
    "dispatch succeeded": (r) => r.status === 201 || r.status === 402,
  });
  errorRate.add(res.status !== 201 && res.status !== 402);

  // Periodically check queue depth
  if (Math.random() < 0.1) {
    const statsRes = http.get(`${BASE_URL}/api/v1/health/queue-stats`);
    if (statsRes.status === 200) {
      const stats = JSON.parse(statsRes.body);
      queueDepth.add(stats.stream_length || 0);
    }
  }
}
