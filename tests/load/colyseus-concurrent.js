import ws from "k6/ws";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const roundTrip = new Trend("ws_round_trip_ms");

const WS_URL = __ENV.WS_URL || "ws://localhost:4303";

export const options = {
  stages: [
    { duration: "15s", target: 25 },
    { duration: "30s", target: 50 },
    { duration: "30s", target: 50 },
    { duration: "15s", target: 0 },
  ],
  thresholds: {
    ws_round_trip_ms: ["p(95)<100"],
  },
};

export default function () {
  const url = `${WS_URL}/office`;
  const res = ws.connect(url, {}, function (socket) {
    socket.on("open", () => {
      // Send movement messages
      for (let i = 0; i < 10; i++) {
        const start = Date.now();
        socket.send(
          JSON.stringify([
            10, // Colyseus message type for room message
            { x: 400 + Math.random() * 100, y: 300 + Math.random() * 100 },
          ])
        );
        roundTrip.add(Date.now() - start);
        sleep(0.1);
      }
    });

    socket.on("message", (msg) => {
      // Process incoming state patches
    });

    socket.setTimeout(() => {
      socket.close();
    }, 10000);
  });

  check(res, {
    "ws connected": (r) => r && r.status === 101,
  });
}
