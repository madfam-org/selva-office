import { BaseEdge, getBezierPath, EdgeLabelRenderer } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';

export function ConditionalEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  data,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const condition = (data as Record<string, unknown>)?.condition as Record<string, string> | null;
  const conditionType = condition
    ? condition.regex
      ? 'regex'
      : condition.keyword
        ? 'keyword'
        : condition.expression
          ? 'expr'
          : ''
    : '';

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? '#818cf8' : '#6366f1',
          strokeWidth: selected ? 2.5 : 1.5,
          strokeDasharray: condition ? '5 3' : undefined,
        }}
      />
      {(label || conditionType) && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-600 text-retro-xs text-slate-300 pixel-text"
          >
            {conditionType && (
              <span className="text-indigo-400 mr-1">[{conditionType}]</span>
            )}
            {label as string}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
