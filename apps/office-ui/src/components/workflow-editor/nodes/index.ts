import { AgentNode } from './AgentNode';
import { BatchNode } from './BatchNode';
import { HumanNode } from './HumanNode';
import { PassthroughNode } from './PassthroughNode';
import { SubgraphNode } from './SubgraphNode';
import { PythonRunnerNode } from './PythonRunnerNode';
import { LiteralNode } from './LiteralNode';
import { LoopCounterNode } from './LoopCounterNode';
import type { NodeTypes } from '@xyflow/react';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const nodeTypes: NodeTypes = {
  agentNode: AgentNode,
  batchNode: BatchNode,
  humanNode: HumanNode,
  passthroughNode: PassthroughNode,
  subgraphNode: SubgraphNode,
  pythonRunnerNode: PythonRunnerNode,
  literalNode: LiteralNode,
  loopCounterNode: LoopCounterNode,
} as unknown as NodeTypes;

export { AgentNode, BatchNode, HumanNode, PassthroughNode, SubgraphNode, PythonRunnerNode, LiteralNode, LoopCounterNode };
