import { Room, Client } from "@colyseus/core";
import {
  OfficeStateSchema,
  DepartmentSchema,
  AgentSchema,
  TacticianSchema,
} from "../schema/OfficeState";
import { handleMovement } from "../handlers/movement";
import { handleInteraction, handleApproval } from "../handlers/interaction";
import { handleChat, addSystemMessage } from "../handlers/chat";
import { handleEmote } from "../handlers/emotes";
import { handleAvatar } from "../handlers/avatar";
import { handleStatus, handleMusicStatus } from "../handlers/status";
import {
  startProximityLoop,
  lockBubble,
  unlockBubble,
  removeFromLockedGroups,
  isInLockedBubble,
} from "../handlers/proximity";
import {
  handleMegaphoneStart,
  handleMegaphoneStop,
  releaseMegaphone,
  getMegaphoneSpeaker,
} from "../handlers/megaphone";
import { handleSignaling } from "../handlers/signaling";
import type { WebRTCSignalMessage } from "../handlers/signaling";
import { handleCompanion } from "../handlers/companion";
import { createLogger } from "@autoswarm/config/logging";
import { getRedisClient, closeRedisClient } from "../redis-client";
import type { RedisClientType } from "redis";

const logger = createLogger({ service: "colyseus" }).child({ component: "OfficeRoom" });

interface MoveMessage {
  x: number;
  y: number;
}

interface InteractMessage {
  agentId: string;
}

interface ApproveMessage {
  requestId: string;
  result: "approved" | "denied";
  feedback?: string;
}

interface ChatMessage {
  content: string;
}

interface EmoteMessage {
  type: string;
}

interface AvatarMessage {
  config: string;
}

interface StatusMessage {
  status: string;
}

interface RoomOptions {
  nexusApiUrl?: string;
  name?: string;
}

const DEFAULT_DEPARTMENTS: Array<{
  id: string;
  name: string;
  slug: string;
  maxAgents: number;
  x: number;
  y: number;
}> = [
  {
    id: "dept-engineering",
    name: "Engineering",
    slug: "engineering",
    maxAgents: 6,
    x: 100,
    y: 100,
  },
  {
    id: "dept-research",
    name: "Research",
    slug: "research",
    maxAgents: 4,
    x: 600,
    y: 100,
  },
  {
    id: "dept-crm",
    name: "CRM",
    slug: "crm",
    maxAgents: 4,
    x: 100,
    y: 400,
  },
  {
    id: "dept-support",
    name: "Support",
    slug: "support",
    maxAgents: 4,
    x: 600,
    y: 400,
  },
  {
    id: "dept-blueprint",
    name: "Blueprint Lab",
    slug: "blueprint",
    maxAgents: 0,
    x: 800,
    y: 260,
  },
];

export class OfficeRoom extends Room<OfficeStateSchema> {
  private nexusApiUrl: string = "http://localhost:4300";
  private stopProximityLoop: (() => void) | null = null;
  private agentIndex = new Map<string, { deptId: string; agentIndex: number }>();
  private redisSubscriber: RedisClientType | null = null;

  onCreate(options: RoomOptions): void {
    logger.info("Room created");

    this.setState(new OfficeStateSchema());

    this.nexusApiUrl =
      options.nexusApiUrl ??
      process.env.NEXUS_API_URL ??
      this.nexusApiUrl;

    for (const dept of DEFAULT_DEPARTMENTS) {
      const department = new DepartmentSchema();
      department.id = dept.id;
      department.name = dept.name;
      department.slug = dept.slug;
      department.maxAgents = dept.maxAgents;
      department.x = dept.x;
      department.y = dept.y;
      this.state.departments.set(dept.id, department);
    }

    this.onMessage("move", (client: Client, message: MoveMessage) => {
      handleMovement(this.state, client, message);
    });

    this.onMessage("interact", (client: Client, message: InteractMessage) => {
      handleInteraction(this.state, client, message);
    });

    this.onMessage("approve", (client: Client, message: ApproveMessage) => {
      handleApproval(this.state, client, {
        ...message,
        nexusApiUrl: this.nexusApiUrl,
      });
    });

    this.onMessage("deny", (client: Client, message: ApproveMessage) => {
      handleApproval(this.state, client, {
        ...message,
        result: "denied",
        nexusApiUrl: this.nexusApiUrl,
      });
    });

    this.onMessage("chat", (client: Client, message: ChatMessage) => {
      handleChat(this.state, client, message);
    });

    this.onMessage("emote", (client: Client, message: EmoteMessage) => {
      handleEmote(this.state, client, message, (type, payload) =>
        this.broadcast(type, payload)
      );
    });

    this.onMessage("avatar", (client: Client, message: AvatarMessage) => {
      handleAvatar(this.state, client, message);
    });

    this.onMessage(
      "webrtc_signal",
      (client: Client, message: WebRTCSignalMessage) => {
        handleSignaling(client, message, () => this.clients);
      }
    );

    this.onMessage("status", (client: Client, message: StatusMessage) => {
      handleStatus(this.state, client, message);
    });

    this.onMessage("music_status", (client: Client, message: { status: string }) => {
      handleMusicStatus(this.state, client, message);
    });

    this.onMessage("lock_bubble", (client: Client) => {
      const locked = lockBubble(client.sessionId, this.state);
      client.send("bubble_lock_status", { locked });
      if (locked) {
        logger.info({ sessionId: client.sessionId }, "Bubble locked");
      }
    });

    this.onMessage("unlock_bubble", (client: Client) => {
      const unlocked = unlockBubble(client.sessionId);
      client.send("bubble_lock_status", { locked: false });
      if (unlocked) {
        logger.info({ sessionId: client.sessionId }, "Bubble unlocked");
      }
    });

    this.onMessage("megaphone_start", (client: Client) => {
      handleMegaphoneStart(this.state, client, (type, payload) =>
        this.broadcast(type, payload)
      );
    });

    this.onMessage("megaphone_stop", (client: Client) => {
      handleMegaphoneStop(client, (type, payload) =>
        this.broadcast(type, payload)
      );
    });

    this.onMessage("companion", (client: Client, message: { type: string }) => {
      handleCompanion(this.state, client, message);
    });

    // Start proximity detection loop at 5Hz for WebRTC peer management
    this.stopProximityLoop = startProximityLoop(
      this.state,
      () => this.clients,
      5
    );

    logger.info(
      { departmentCount: DEFAULT_DEPARTMENTS.length },
      "Initialized with departments"
    );

    // Fire-and-forget: populate agents from nexus-api database.
    this.fetchAgentsFromApi().catch((err) =>
      logger.error({ err }, "Failed to fetch agents")
    );

    // Fire-and-forget: subscribe to real-time agent status updates via Redis.
    this.subscribeToAgentUpdates().catch((err) =>
      logger.error({ err }, "Failed to subscribe to agent updates")
    );
  }

  onJoin(client: Client, options?: RoomOptions & { name?: string }): void {
    logger.info({ sessionId: client.sessionId }, "Client joined");

    const player = new TacticianSchema();
    player.sessionId = client.sessionId;
    player.name = options?.name ?? "Player";
    player.x = 400;
    player.y = 300;
    player.direction = "down";
    this.state.players.set(client.sessionId, player);

    addSystemMessage(this.state, `${player.name} joined`);
    this.broadcast("player_joined", {
      sessionId: client.sessionId,
      name: player.name,
    });
  }

  onLeave(client: Client, consented: boolean): void {
    logger.info(
      { sessionId: client.sessionId, consented },
      "Client left"
    );

    const player = this.state.players.get(client.sessionId);
    const name = player?.name ?? "Player";
    this.state.players.delete(client.sessionId);
    removeFromLockedGroups(client.sessionId);
    releaseMegaphone(client.sessionId, (type, payload) =>
      this.broadcast(type, payload)
    );

    addSystemMessage(this.state, `${name} left`);
    this.broadcast("player_left", { sessionId: client.sessionId });
  }

  onDispose(): void {
    logger.info("Room disposed");
    if (this.stopProximityLoop) {
      this.stopProximityLoop();
      this.stopProximityLoop = null;
    }
    if (this.redisSubscriber) {
      this.redisSubscriber.quit().catch(() => {});
    }
  }

  // -- Agent sync from database -----------------------------------------------

  private async fetchAgentsFromApi(): Promise<void> {
    // Build a slug->colyseus-dept map for matching API departments to state.
    const slugToDept = new Map<string, { stateKey: string; dept: DepartmentSchema }>();
    this.state.departments.forEach((dept, key) => {
      slugToDept.set(dept.slug, { stateKey: key, dept });
    });

    // Fetch the department list from the API (which uses real UUID IDs).
    let apiDepts: Array<Record<string, any>>;
    try {
      const listResp = await fetch(
        `${this.nexusApiUrl}/api/v1/departments/`,
        { headers: { Authorization: "Bearer dev-token" } }
      );
      if (!listResp.ok) {
        logger.error(
          { statusCode: listResp.status },
          "Failed to fetch department list"
        );
        return;
      }
      apiDepts = (await listResp.json()) as Array<Record<string, any>>;
    } catch (err) {
      logger.error({ err }, "Failed to fetch department list");
      return;
    }

    // For each API department, fetch its detail (with agents) and populate state.
    for (const apiDept of apiDepts) {
      const match = slugToDept.get(apiDept.slug as string);
      if (!match) continue;
      const { stateKey, dept } = match;

      try {
        const resp = await fetch(
          `${this.nexusApiUrl}/api/v1/departments/${apiDept.id}`,
          { headers: { Authorization: "Bearer dev-token" } }
        );
        if (!resp.ok) continue;
        const detail = (await resp.json()) as Record<string, any>;
        const agents = (detail.agents ?? []) as Array<Record<string, any>>;
        for (let i = 0; i < agents.length; i++) {
          const a = agents[i];
          const agent = new AgentSchema();
          agent.id = a.id;
          agent.name = a.name;
          agent.role = a.role;
          agent.status = a.status ?? "idle";
          agent.level = a.level ?? 1;
          agent.x = dept.x + 48 + (i % 3) * 48;
          agent.y = dept.y + 48 + Math.floor(i / 3) * 48;
          agent.currentTaskId = a.current_task_id ?? "";
          agent.currentTaskDescription = "";
          agent.departmentId = stateKey;
          const skills = (a.effective_skills ?? []) as string[];
          for (const skill of skills) {
            agent.skills.push(skill);
          }
          dept.agents.push(agent);
        }
        logger.info(
          { agentCount: agents.length, deptSlug: dept.slug, deptKey: stateKey },
          "Loaded agents into department"
        );
      } catch (err) {
        logger.error(
          { err, deptSlug: dept.slug },
          "Failed to fetch agents for department"
        );
      }
    }
    this.rebuildAgentIndex();
  }

  private async subscribeToAgentUpdates(): Promise<void> {
    try {
      this.redisSubscriber = await getRedisClient();
    } catch (err) {
      logger.error(
        { err },
        "Redis subscriber failed to connect (room will work without real-time agent updates)"
      );
      return;
    }

    await this.redisSubscriber.subscribe(
      "autoswarm:agent-status",
      (message: string) => {
        try {
          const update = JSON.parse(message) as {
            agent_id: string;
            status: string;
            task_id?: string;
            task_description?: string;
            current_node_id?: string;
          };
          this.updateAgentInState(
            update.agent_id,
            update.status,
            update.task_id,
            update.task_description,
            update.current_node_id
          );
        } catch (err) {
          logger.error({ err }, "Bad agent-status message");
        }
      }
    );
    logger.info("Subscribed to autoswarm:agent-status channel");
  }

  private rebuildAgentIndex(): void {
    this.agentIndex.clear();
    this.state.departments.forEach((dept, deptId) => {
      for (let i = 0; i < dept.agents.length; i++) {
        const agent = dept.agents.at(i);
        if (agent) {
          this.agentIndex.set(agent.id, { deptId, agentIndex: i });
        }
      }
    });
  }

  private updateAgentInState(
    agentId: string,
    status: string,
    taskId?: string,
    taskDescription?: string,
    currentNodeId?: string
  ): void {
    const applyUpdate = (agent: AgentSchema): void => {
      agent.status = status;
      if (taskId !== undefined) {
        agent.currentTaskId = taskId;
      }
      if (taskDescription !== undefined) {
        agent.currentTaskDescription = taskDescription;
      }
      if (currentNodeId !== undefined) {
        agent.currentNodeId = currentNodeId;
      }
      // Clear task fields when agent returns to idle
      if (status === "idle" && taskId === undefined) {
        agent.currentTaskId = "";
        agent.currentTaskDescription = "";
        agent.currentNodeId = "";
      }
      if (status === "waiting_approval") {
        this.state.pendingApprovalCount += 1;
        addSystemMessage(
          this.state,
          `Agent ${agent.name} is waiting for approval`
        );
      }
    };

    const entry = this.agentIndex.get(agentId);
    if (entry) {
      const dept = this.state.departments.get(entry.deptId);
      const agent = dept?.agents.at(entry.agentIndex);
      if (agent && agent.id === agentId) {
        applyUpdate(agent);
        return;
      }
    }

    // Fallback: linear scan (index may be stale)
    let found = false;
    this.state.departments.forEach((dept) => {
      if (found) return;
      for (let i = 0; i < dept.agents.length; i++) {
        const agent = dept.agents.at(i);
        if (agent && agent.id === agentId) {
          applyUpdate(agent);
          found = true;
          return;
        }
      }
    });

    if (!found) {
      logger.warn(
        { agentId },
        "Agent not found in any department"
      );
    }
  }
}
