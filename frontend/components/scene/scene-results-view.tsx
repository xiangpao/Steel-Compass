"use client";

import { useState } from "react";
import { AlertTriangle, Archive, Check, Copy, GitCompare, Pencil, X } from "lucide-react";
import { evidenceStatus } from "@/lib/evidence-status";
import { STATUS_LABELS, controllingUtilization } from "@/lib/scene-model";
import type { SceneInstance, SceneRevision } from "@/lib/types";

export function sceneResultTitle(revision: SceneRevision | null, stale: boolean) {
  if (!revision) return "尚未计算";
  if (stale) return "输入已修改，结果已过期";
  return `当前输入和适用范围内${evidenceStatus(revision.scene_result).headline}`;
}

function RenameField({
  title,
  onSubmit,
  onCancel,
}: {
  title: string;
  onSubmit: (title: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(title);
  return (
    <form
      className="comparison-rename"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(value.trim());
      }}
    >
      <input
        aria-label="方案名称"
        value={value}
        autoFocus
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
        }}
      />
      <button type="submit" aria-label="保存方案名称" disabled={!value.trim()}>
        <Check size={14} />
      </button>
      <button type="button" aria-label="取消重命名" onClick={onCancel}>
        <X size={14} />
      </button>
    </form>
  );
}

function ComparisonSection({
  instances,
  currentInstanceId,
  revisionsByInstance,
  onOpen,
  onRename,
  onArchive,
}: {
  instances: SceneInstance[];
  currentInstanceId?: number;
  revisionsByInstance: Record<number, SceneRevision[]>;
  onOpen: (instance: SceneInstance) => void;
  onRename: (instance: SceneInstance, title: string) => void;
  onArchive: (instance: SceneInstance) => void;
}) {
  const [renamingId, setRenamingId] = useState<number | null>(null);
  return (
    <section className="comparison-section">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">OPTION COMPARISON</span>
          <h2>方案对比</h2>
        </div>
        <span>{instances.length}/3</span>
      </div>
      {instances.length ? (
        <div className="comparison-grid">
          {instances.map((alternative) => {
            const comparedRevision = revisionsByInstance[alternative.id]?.[0];
            const comparedMaterial = alternative.draft_state.material_system as string | undefined;
            return (
              <article key={alternative.id} className={alternative.id === currentInstanceId ? "active" : ""}>
                <div className="comparison-card-heading">
                  {renamingId === alternative.id ? (
                    <RenameField
                      title={alternative.title}
                      onCancel={() => setRenamingId(null)}
                      onSubmit={(title) => {
                        setRenamingId(null);
                        if (title && title !== alternative.title) onRename(alternative, title);
                      }}
                    />
                  ) : (
                    <>
                      <strong>{alternative.title}</strong>
                      <span>
                        <button aria-label={`重命名${alternative.title}`} onClick={() => setRenamingId(alternative.id)}>
                          <Pencil size={14} />
                        </button>
                        <button aria-label={`归档${alternative.title}`} onClick={() => onArchive(alternative)}>
                          <Archive size={14} />
                        </button>
                      </span>
                    </>
                  )}
                </div>
                <span>{comparedRevision ? `修订 ${comparedRevision.revision_number}` : "尚未计算"}</span>
                <dl>
                  <div>
                    <dt>控制利用率</dt>
                    <dd>{comparedRevision ? controllingUtilization(comparedRevision)?.toFixed(3) ?? "—" : "—"}</dd>
                  </div>
                  <div>
                    <dt>材料体系</dt>
                    <dd>{comparedMaterial ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>结论</dt>
                    <dd>{comparedRevision ? evidenceStatus(comparedRevision.scene_result).headline : "待计算"}</dd>
                  </div>
                </dl>
                <small>{comparedRevision?.report_number ?? "草稿"}</small>
                <button className="quiet-button" onClick={() => onOpen(alternative)}>
                  打开方案
                </button>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="panel-description">计算后可复制为方案 A/B/C，并排比较控制利用率和主要参数。</p>
      )}
    </section>
  );
}

function ResultDetails({ revision }: { revision: SceneRevision }) {
  const result = revision.scene_result;
  const checks = Object.entries(revision.result_bundle)
    .flatMap(([nodeId, nodeResult]) => nodeResult.checks.map((check) => ({ nodeId, check })))
    .sort((a, b) => b.check.utilization - a.check.utilization)
    .slice(0, 8);
  const combinations = Object.entries(revision.result_bundle)
    .flatMap(([nodeId, nodeResult]) => [
      ...nodeResult.combinations.slice(0, 2).map((combination) => ({
        key: `${nodeId}-${combination.name}`,
        label: combination.name,
        value: `${combination.total.value.toFixed(3)} ${combination.total.unit}`,
      })),
      ...Object.entries(nodeResult.reactions)
        .slice(0, 4)
        .map(([name, value]) => ({
          key: `${nodeId}-${name}`,
          label: `${nodeId} · ${name}`,
          value: `${value.value.toFixed(3)} ${value.unit}`,
        })),
    ])
    .slice(0, 10);
  return (
    <section className="result-detail-grid" aria-label="计算结果详情">
      <article>
        <h3>控制验算</h3>
        {checks.map(({ nodeId, check }) => (
          <div className="result-data-row" key={`${nodeId}-${check.name}`}>
            <span>
              {check.name}
              <small>{nodeId}</small>
            </span>
            <strong>{(check.utilization * 100).toFixed(1)}%</strong>
          </div>
        ))}
      </article>
      <article>
        <h3>控制组合与反力</h3>
        {result.seismic_action_package && (
          <>
            <div className="result-data-row">
              <span>地震设计状况 · G_eq</span>
              <strong>{result.seismic_action_package.gravity_representative_value_kn.toFixed(3)} kN</strong>
            </div>
            <div className="result-data-row">
              <span>±X / ±Y 等效地震作用</span>
              <strong>±{result.seismic_action_package.f_ek_kn.toFixed(3)} kN</strong>
            </div>
          </>
        )}
        {combinations.map((item) => (
          <div className="result-data-row" key={item.key}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </article>
      <article>
        <h3>覆盖范围与缺失资料</h3>
        <p>
          {result.completed_nodes}/{result.total_required_nodes} 个必选节点已处理
        </p>
        {Object.values(result.node_results).map((node) => (
          <div className="result-data-row" key={node.node_id}>
            <span>{node.label}</span>
            <strong>{node.applicability === "not_applicable" ? "不适用" : STATUS_LABELS[node.status]}</strong>
          </div>
        ))}
        {result.missing_nodes.map((item) => (
          <p className="missing-data" key={item}>
            缺失：{item}
          </p>
        ))}
      </article>
    </section>
  );
}

export function SceneResultsView({
  revision,
  stale,
  working,
  instance,
  comparisonInstances,
  revisionsByInstance,
  onEditSettings,
  onDuplicate,
  onRecalculate,
  onSelectRevision,
  onOpenInstance,
  onRenameInstance,
  onArchiveInstance,
}: {
  revision: SceneRevision | null;
  stale: boolean;
  working: boolean;
  instance: SceneInstance | null;
  comparisonInstances: SceneInstance[];
  revisionsByInstance: Record<number, SceneRevision[]>;
  onEditSettings: () => void;
  onDuplicate: () => void;
  onRecalculate: () => void;
  onSelectRevision: (revision: SceneRevision) => void;
  onOpenInstance: (instance: SceneInstance) => void;
  onRenameInstance: (instance: SceneInstance, title: string) => void;
  onArchiveInstance: (instance: SceneInstance) => void;
}) {
  const history = revisionsByInstance[instance?.id ?? -1] ?? [];
  const evidence = revision ? evidenceStatus(revision.scene_result) : null;
  const spaceFrame = revision?.scene_result.space_frame_analysis;
  return (
    <div className="results-workbench">
      <div className={`scene-summary ${revision?.scene_result.status ?? "empty"} ${stale ? "stale" : ""}`}>
        <div>
          <strong>{sceneResultTitle(revision, stale)}</strong>
          <span>
            {revision
              ? `${revision.scene_result.completed_nodes}/${revision.scene_result.total_required_nodes} 个必选节点 · ${evidence!.qualifier}`
              : "完成设置后即可生成可追溯修订"}
          </span>
        </div>
        {revision && (
          <div>
            <strong>{controllingUtilization(revision)?.toFixed(3) ?? "—"}</strong>
            <span>控制利用率 · 报告号 {revision.report_number}</span>
          </div>
        )}
      </div>

      {revision ? (
        <>
          <div className="result-action-row">
            <button className="secondary-button" onClick={onEditSettings}>
              修改参数
            </button>
            <a
              className="secondary-button"
              href={`/api/v2/projects/${revision.project_id}/revisions/${revision.id}/report.pdf`}
              target="_blank"
              rel="noreferrer"
            >
              下载 PDF 报告
            </a>
            <button className="secondary-button" disabled={stale || comparisonInstances.length >= 3 || working} onClick={onDuplicate}>
              <Copy size={16} /> 复制为方案 {String.fromCharCode(65 + comparisonInstances.length)}
            </button>
            <button className="primary-button" disabled={working} onClick={onRecalculate}>
              {working ? "计算中…" : "重新计算"}
            </button>
          </div>
          <div className="result-warning-list">
            {revision.scene_result.warnings.map((warning) => (
              <p key={warning}>
                <AlertTriangle size={15} />
                {warning}
              </p>
            ))}
          </div>
          {spaceFrame && (
            <div className="space-frame-result-card">
              <div>
                <strong>三维杆系分析</strong>
                <span>{spaceFrame.solver} · 未独立验证</span>
              </div>
              <dl>
                <div>
                  <dt>模型规模</dt>
                  <dd>
                    {spaceFrame.node_count} 节点 / {spaceFrame.member_count} 杆件
                  </dd>
                </div>
                <div>
                  <dt>屋面面积</dt>
                  <dd>{spaceFrame.roof_area_m2.toFixed(2)} m²</dd>
                </div>
                <div>
                  <dt>最大空间位移</dt>
                  <dd>{spaceFrame.maximum_translation_mm.toFixed(3)} mm</dd>
                </div>
                <div>
                  <dt>支座反力组</dt>
                  <dd>{Object.keys(spaceFrame.support_reactions).length} 组</dd>
                </div>
              </dl>
              <p>{spaceFrame.load_scope}</p>
            </div>
          )}
          {history.length > 1 && (
            <label className="revision-selector">
              <span>查看历史修订</span>
              <select
                value={revision.id}
                onChange={(event) => {
                  const selected = history.find((item) => item.id === Number(event.target.value));
                  if (selected) onSelectRevision(selected);
                }}
              >
                {history.map((item) => (
                  <option key={item.id} value={item.id}>
                    修订 {item.revision_number} · {item.report_number}
                  </option>
                ))}
              </select>
            </label>
          )}
          <ResultDetails revision={revision} />
        </>
      ) : (
        <div className="empty-result">
          <GitCompare size={28} />
          <strong>尚未生成场景结果</strong>
          <span>设置和结果只有两个页面，不需要逐步退出或重新选择场景。</span>
          <button className="primary-button" onClick={onEditSettings}>
            返回设置
          </button>
        </div>
      )}

      <ComparisonSection
        instances={comparisonInstances}
        currentInstanceId={instance?.id}
        revisionsByInstance={revisionsByInstance}
        onOpen={onOpenInstance}
        onRename={onRenameInstance}
        onArchive={onArchiveInstance}
      />
    </div>
  );
}
