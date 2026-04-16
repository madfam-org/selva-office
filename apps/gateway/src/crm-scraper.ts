/**
 * CRM scraper for Phyne-CRM integration.
 *
 * Fetches open leads, overdue activities, and hot leads from the Phyne-CRM
 * tRPC API and converts them into ExternalEvent objects for the HeartbeatService.
 */

import type pino from "pino";

interface ExternalEvent {
  source: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

interface TRPCResponse<T = unknown> {
  result?: { data?: T };
}

interface PhyneLead {
  id: string;
  contact_id: string;
  stage_id: string;
  stage_name?: string;
  score?: number;
  status?: string;
}

interface PhyneActivity {
  id: string;
  type: string;
  title: string;
  status?: string;
  due_date?: string;
  entity_type?: string;
  entity_id?: string;
}

export class CRMScraper {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly logger: pino.Logger;

  constructor(baseUrl: string, token: string = "", logger: pino.Logger) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
    this.logger = logger;
  }

  async scrape(): Promise<ExternalEvent[]> {
    const events: ExternalEvent[] = [];
    const now = new Date().toISOString();

    try {
      // Fetch open leads
      const leads = await this.fetchLeads("open");
      for (const lead of leads) {
        if (lead.score != null && lead.score > 80) {
          events.push({
            source: "crm",
            type: "hot_lead",
            payload: {
              lead_id: lead.id,
              contact_id: lead.contact_id,
              score: lead.score,
              stage: lead.stage_name ?? lead.stage_id,
            },
            timestamp: now,
          });
        } else {
          events.push({
            source: "crm",
            type: "lead_followup",
            payload: {
              lead_id: lead.id,
              contact_id: lead.contact_id,
              stage: lead.stage_name ?? lead.stage_id,
            },
            timestamp: now,
          });
        }
      }

      // Fetch overdue activities
      const activities = await this.fetchActivities();
      for (const activity of activities) {
        if (this.isOverdue(activity)) {
          events.push({
            source: "crm",
            type: "activity_overdue",
            payload: {
              activity_id: activity.id,
              title: activity.title,
              type: activity.type,
              due_date: activity.due_date,
              entity_type: activity.entity_type,
              entity_id: activity.entity_id,
            },
            timestamp: now,
          });
        }
      }
    } catch (err) {
      this.logger.error({ err }, "CRM scrape failed");
    }

    return events;
  }

  private async fetchLeads(status?: string): Promise<PhyneLead[]> {
    const input = status ? JSON.stringify({ status }) : undefined;
    const url = `${this.baseUrl}/api/trpc/leads.list${input ? `?input=${encodeURIComponent(input)}` : ""}`;

    const response = await fetch(url, {
      headers: this.headers(),
    });

    if (!response.ok) {
      this.logger.error({ statusCode: response.status }, "leads.list request failed");
      return [];
    }

    const json = (await response.json()) as TRPCResponse;
    // tRPC with superjson: { result: { data: { json: { items: [...] } } } }
    // tRPC without superjson: { result: { data: [...] } }
    const data = json.result?.data;
    const leads: PhyneLead[] = Array.isArray(data)
      ? data
      : (data as any)?.json?.items ?? (data as any)?.items ?? [];
    return leads;
  }

  private async fetchActivities(): Promise<PhyneActivity[]> {
    const url = `${this.baseUrl}/api/trpc/activities.listForEntity?input=${encodeURIComponent(JSON.stringify({ type: "all", id: "" }))}`;

    const response = await fetch(url, {
      headers: this.headers(),
    });

    if (!response.ok) {
      this.logger.error(
        { statusCode: response.status },
        "activities.listForEntity request failed"
      );
      return [];
    }

    const json = (await response.json()) as TRPCResponse;
    const data = json.result?.data;
    const activities: PhyneActivity[] = Array.isArray(data)
      ? data
      : (data as any)?.json?.items ?? (data as any)?.items ?? [];
    return activities.filter(
      (a) => a.status === "pending" || a.status === "overdue"
    );
  }

  private isOverdue(activity: PhyneActivity): boolean {
    if (!activity.due_date) return false;
    return new Date(activity.due_date) < new Date();
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.token) {
      h["Authorization"] = `Bearer ${this.token}`;
    }
    return h;
  }
}
