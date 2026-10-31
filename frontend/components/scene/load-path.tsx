"use client";

import { Check, CircleDot } from "lucide-react";
import { STATUS_LABELS } from "@/lib/scene-model";
import type { SceneGraphTemplate, SceneRevision } from "@/lib/types";

export function LoadPath({
  nodes,
  revision,
  stale,
  compact = false,
}: {
  nodes: SceneGraphTemplate["nodes"];
  revision: SceneRevision | null;
  stale: boolean;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "load-path compact" : "load-path"}>
      {nodes.map((node, index) => {
        const result = revision?.scene_result.node_results[node.id];
        return (
          <div className="load-path-item" key={node.id}>
            <span className={`path-dot ${result?.status ?? node.maturity}`}>
              {result?.status === "passed" || result?.status === "completed" ? <Check size={13} /> : <CircleDot size={13} />}
            </span>
            <div>
              <strong>{node.label}</strong>
              <span>
                {result ? STATUS_LABELS[result.status] : node.quick_assumption ? "快算假定待确认" : "待计算"}
                {stale || result?.stale ? " · 已过期" : ""}
              </span>
              {node.quick_assumption && !result && <small>{node.quick_assumption}</small>}
              {result?.message && <small>{result.message}</small>}
            </div>
            {index < nodes.length - 1 && <span className="path-line" />}
          </div>
        );
      })}
    </div>
  );
}
