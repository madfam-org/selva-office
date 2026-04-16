import { CronJob } from "cron";
import { Octokit } from "@octokit/rest";
import WebSocket from "ws";
import type pino from "pino";
import { CRMScraper } from "./crm-scraper";

interface ExternalEvent {
  source: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

interface EnemyWaveEvent {
  kind: "enemy_wave" | "alert" | "report";
  source: string;
  events: ExternalEvent[];
  compiledAt: string;
}

export class HeartbeatService {
  private readonly nexusApiUrl: string;
  private readonly cronExpression: string;
  private cronJob: CronJob | null = null;
  private ws: WebSocket | null = null;
  private readonly crmScraper: CRMScraper | null;
  private readonly logger: pino.Logger;

  private _lastTickTime: string | null = null;
  private _totalTicks: number = 0;

  constructor(
    nexusApiUrl: string,
    cronExpression: string = "*/30 * * * *",
    logger: pino.Logger
  ) {
    this.nexusApiUrl = nexusApiUrl;
    this.cronExpression = cronExpression;
    this.logger = logger;

    const phyneCrmUrl = process.env.PHYNE_CRM_URL;
    const phyneCrmToken = process.env.PHYNE_CRM_TOKEN ?? "";
    const crmLogger = logger.child({ component: "crm-scraper" });
    this.crmScraper = phyneCrmUrl
      ? new CRMScraper(phyneCrmUrl, phyneCrmToken, crmLogger)
      : null;
  }

  /** ISO timestamp of the last completed tick, or null if no tick has run. */
  get lastTickTime(): string | null {
    return this._lastTickTime;
  }

  /** ISO timestamp of the next scheduled tick, or null if not running. */
  get nextTickTime(): string | null {
    if (!this.cronJob) return null;
    try {
      const next = this.cronJob.nextDate();
      return next.toISO();
    } catch {
      return null;
    }
  }

  /** Total number of ticks executed since the service started. */
  get totalTicks(): number {
    return this._totalTicks;
  }

  start(): void {
    this.cronJob = new CronJob(this.cronExpression, () => {
      this.tick().catch((err) => {
        this.logger.error({ err }, "Error during tick");
      });
    });
    this.cronJob.start();
    this.logger.info("CronJob started");
  }

  stop(): void {
    if (this.cronJob) {
      this.cronJob.stop();
      this.cronJob = null;
      this.logger.info("CronJob stopped");
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.logger.info("WebSocket closed");
    }
  }

  async tick(): Promise<void> {
    const timestamp = new Date().toISOString();
    this.logger.info({ timestamp }, "Tick started");

    const crmEvents = await this.scrapeCRM();
    const githubEvents = await this.scrapeGitHub();
    const ticketEvents = await this.scrapeTickets();

    const allEvents = [...crmEvents, ...githubEvents, ...ticketEvents];

    const waves = this.compileEnemyWaves(allEvents);

    if (waves.length > 0) {
      await this.dispatch(waves);
    } else {
      this.logger.info("No events to dispatch this cycle");
    }

    this._lastTickTime = timestamp;
    this._totalTicks += 1;
  }

  private async scrapeCRM(): Promise<ExternalEvent[]> {
    if (!this.crmScraper) {
      this.logger.info("PHYNE_CRM_URL not set; skipping CRM scrape");
      return [];
    }

    try {
      this.logger.info("Scraping CRM via Phyne-CRM...");
      return await this.crmScraper.scrape();
    } catch (err) {
      this.logger.error({ err }, "CRM scrape failed");
      return [];
    }
  }

  private async scrapeGitHub(): Promise<ExternalEvent[]> {
    const token = process.env.GITHUB_TOKEN;
    const reposEnv = process.env.GITHUB_REPOS;
    if (!token || !reposEnv) {
      this.logger.info("GITHUB_TOKEN or GITHUB_REPOS not set; skipping GitHub scrape");
      return [];
    }

    const repos = reposEnv.split(",").map((r) => r.trim()).filter(Boolean);
    const octokit = new Octokit({ auth: token });
    const events: ExternalEvent[] = [];
    const now = new Date().toISOString();

    for (const repo of repos) {
      const [owner, name] = repo.split("/");
      if (!owner || !name) continue;

      try {
        // Fetch open PRs with review requests (max 10)
        const { data: prs } = await octokit.pulls.list({
          owner,
          repo: name,
          state: "open",
          per_page: 10,
        });

        for (const pr of prs) {
          if (pr.requested_reviewers && pr.requested_reviewers.length > 0) {
            events.push({
              source: "github",
              type: "pr_review_requested",
              payload: {
                repo,
                pr_number: pr.number,
                title: pr.title,
                author: pr.user?.login ?? "unknown",
                reviewers: pr.requested_reviewers.map((r) => r.login),
                url: pr.html_url,
              },
              timestamp: now,
            });
          }

          // Check CI status on head commit
          try {
            const { data: status } = await octokit.repos.getCombinedStatusForRef({
              owner,
              repo: name,
              ref: pr.head.sha,
            });

            if (status.state === "failure") {
              events.push({
                source: "github",
                type: "ci_failure",
                payload: {
                  repo,
                  pr_number: pr.number,
                  title: pr.title,
                  sha: pr.head.sha,
                  url: pr.html_url,
                },
                timestamp: now,
              });
            }
          } catch {
            // CI status may not be available for all commits
          }
        }

        // Fetch issues labeled 'critical' (max 5)
        const { data: issues } = await octokit.issues.listForRepo({
          owner,
          repo: name,
          labels: "critical",
          state: "open",
          per_page: 5,
        });

        for (const issue of issues) {
          if (issue.pull_request) continue; // skip PRs in issues endpoint
          events.push({
            source: "github",
            type: "escalation",
            payload: {
              repo,
              issue_number: issue.number,
              title: issue.title,
              url: issue.html_url,
              labels: issue.labels
                .map((l) => (typeof l === "string" ? l : l.name))
                .filter(Boolean),
            },
            timestamp: now,
          });
        }

        this.logger.info(
          { eventCount: events.length, repo },
          "GitHub scrape completed for repo"
        );
      } catch (err) {
        this.logger.error({ err, repo }, "GitHub scrape failed for repo");
      }
    }

    return events;
  }

  private async scrapeTickets(): Promise<ExternalEvent[]> {
    if (!this.crmScraper) {
      this.logger.info("PHYNE_CRM_URL not set; skipping ticket scrape");
      return [];
    }

    try {
      this.logger.info("Scraping support tickets via Phyne-CRM...");
      const events = await this.crmScraper.scrape();
      // Filter for task-type activities only (ticket-like items)
      return events.filter((e) => e.type === "activity_overdue");
    } catch (err) {
      this.logger.error({ err }, "Ticket scrape failed");
      return [];
    }
  }

  private compileEnemyWaves(events: ExternalEvent[]): EnemyWaveEvent[] {
    if (events.length === 0) {
      return [];
    }

    const now = new Date().toISOString();
    const bySource = new Map<string, ExternalEvent[]>();

    for (const event of events) {
      const existing = bySource.get(event.source) ?? [];
      existing.push(event);
      bySource.set(event.source, existing);
    }

    const waves: EnemyWaveEvent[] = [];

    for (const [source, sourceEvents] of bySource) {
      const hasUrgent = sourceEvents.some(
        (e) => e.type === "escalation" || e.type === "sla_breach"
      );

      waves.push({
        kind: hasUrgent ? "alert" : "enemy_wave",
        source,
        events: sourceEvents,
        compiledAt: now,
      });
    }

    return waves;
  }

  // Auto-dispatch rules: map event types to SwarmTask graph types + skills
  private static readonly AUTO_DISPATCH_RULES: Record<
    string,
    { graphType: string; skills: string[]; hitl: boolean }
  > = {
    "github:pr_opened": { graphType: "review", skills: ["code-review"], hitl: false },
    "github:ci_failed": { graphType: "coding", skills: ["coding", "webapp-testing"], hitl: true },
    "github:issue_opened": { graphType: "research", skills: ["research"], hitl: false },
    "crm:hot_lead": { graphType: "crm", skills: ["crm-outreach"], hitl: false },
    "crm:high_intent_lead": { graphType: "crm", skills: ["crm-outreach"], hitl: false },
    "crm:lead_followup": { graphType: "crm", skills: ["crm-outreach"], hitl: false },
    "crm:activity_overdue": { graphType: "support", skills: ["customer-support"], hitl: false },
    "crm:support_ticket": { graphType: "support", skills: ["customer-support"], hitl: false },
    "crm:campaign_due": { graphType: "research", skills: ["research", "doc-coauthoring"], hitl: false },
  };

  private async dispatch(waves: EnemyWaveEvent[]): Promise<void> {
    // 1. Send waves to WebSocket (existing behavior for UI)
    try {
      const ws = this.getOrCreateWebSocket();
      await this.waitForOpen(ws);
      for (const wave of waves) {
        ws.send(JSON.stringify({ type: "gateway:wave", data: wave }));
        this.logger.info(
          { kind: wave.kind, source: wave.source, eventCount: wave.events.length },
          "Dispatched wave to WebSocket"
        );
      }
    } catch (err) {
      this.logger.error({ err }, "Failed to dispatch waves to WebSocket");
    }

    // 2. Auto-dispatch matching events as SwarmTasks (new behavior)
    if (process.env.AUTO_DISPATCH_ENABLED !== "true") return;

    const dispatchUrl = process.env.NEXUS_API_URL ?? this.nexusApiUrl.replace("ws", "http");
    const token = process.env.WORKER_API_TOKEN;
    if (!token || token === "dev-bypass") {
      this.logger.error("AUTO_DISPATCH_ENABLED but WORKER_API_TOKEN not set or is dev-bypass — skipping dispatch");
      return;
    }

    for (const wave of waves) {
      for (const event of wave.events) {
        const eventKey = `${event.source}:${event.type}`;
        const rule = HeartbeatService.AUTO_DISPATCH_RULES[eventKey];
        if (!rule) continue;

        const description = `[auto] ${event.source}/${event.type}: ${JSON.stringify(event.payload).substring(0, 200)}`;

        try {
          const resp = await fetch(`${dispatchUrl}/api/v1/swarms/dispatch`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              description,
              graph_type: rule.graphType,
              required_skills: rule.skills,
              metadata: { auto_dispatched: true, source_event: eventKey, ...event.payload },
            }),
          });

          if (resp.ok) {
            this.logger.info({ eventKey, graphType: rule.graphType }, "Auto-dispatched SwarmTask");
          } else {
            this.logger.warn({ eventKey, status: resp.status }, "Auto-dispatch failed");
          }
        } catch (err) {
          this.logger.error({ err, eventKey }, "Auto-dispatch error");
        }
      }
    }
  }

  private getOrCreateWebSocket(): WebSocket {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return this.ws;
    }

    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.close();
    }

    this.ws = new WebSocket(this.nexusApiUrl);

    this.ws.on("open", () => {
      this.logger.info("WebSocket connected to nexus-api");
    });

    this.ws.on("error", (err) => {
      this.logger.error({ err }, "WebSocket error");
    });

    this.ws.on("close", (code, reason) => {
      this.logger.info(
        { code, reason: reason.toString() },
        "WebSocket closed"
      );
      this.ws = null;
    });

    return this.ws;
  }

  private waitForOpen(ws: WebSocket): Promise<void> {
    if (ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }

    return new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error("WebSocket connection timeout (10s)"));
      }, 10_000);

      ws.once("open", () => {
        clearTimeout(timeout);
        resolve();
      });

      ws.once("error", (err) => {
        clearTimeout(timeout);
        reject(err);
      });
    });
  }
}
