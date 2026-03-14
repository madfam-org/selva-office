/**
 * TypeScript equivalents of the Python workflow schema
 * (packages/workflows/src/autoswarm_workflows/schema.py).
 *
 * These types are used by the visual workflow editor and API layer.
 */

export type NodeType =
  | 'agent'
  | 'human'
  | 'passthrough'
  | 'subgraph'
  | 'python_runner'
  | 'literal'
  | 'loop_counter';

export type ContextWindowPolicy = 'keep_all' | 'keep_last_n' | 'clear_all' | 'sliding_window';

export type ThinkingStage = 'pre_gen' | 'post_gen';

export interface ContextPolicyConfig {
  type: ContextWindowPolicy;
  n: number;
}

export interface NodeDefinition {
  id: string;
  type: NodeType;
  label: string;

  // Agent node config
  model?: string | null;
  system_prompt?: string | null;
  tools: string[];
  temperature?: number | null;

  // Human node config
  interrupt_message: string;

  // Subgraph node config
  subgraph_id?: string | null;

  // Python runner config
  code?: string | null;

  // Literal node config
  literal_value?: unknown;

  // Loop counter config
  max_iterations: number;

  // Context policy
  context_policy: ContextPolicyConfig;

  // Thinking stages
  thinking_stages: ThinkingStage[];

  // Position in visual editor
  position_x: number;
  position_y: number;
}

export interface TriggerCondition {
  regex?: string | null;
  keyword?: string | null;
  expression?: string | null;
}

export interface EdgeDefinition {
  source: string;
  target: string;
  label: string;
  condition?: TriggerCondition | null;
  carry_data: boolean;
  transform?: string | null;
}

export interface WorkflowDefinition {
  name: string;
  version: string;
  description: string;
  nodes: NodeDefinition[];
  edges: EdgeDefinition[];
  variables: Record<string, unknown>;
  entry_node?: string | null;
}

/** Default values matching the Python schema defaults */
export function createDefaultNode(type: NodeType, id: string): NodeDefinition {
  return {
    id,
    type,
    label: '',
    tools: [],
    interrupt_message: 'Awaiting human approval',
    max_iterations: 5,
    context_policy: { type: 'keep_all', n: 10 },
    thinking_stages: [],
    position_x: 0,
    position_y: 0,
  };
}

export function createDefaultEdge(source: string, target: string): EdgeDefinition {
  return {
    source,
    target,
    label: '',
    carry_data: true,
  };
}
