import { useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Check, Download, Gauge, Save, X } from "lucide-react";
import { PanelHeader } from "@/components/workspace/panel-header";
import { evidenceStatus } from "@/lib/evidence-status";
import type { CalculationResult, ProjectVersion } from "@/lib/types";

export type SavedRevision = {
  id: number;
  project_id: number;
  revision_number: number;
  report_number: string;
};

const TONE_ICON = { passed: Check, completed: Check, incomplete: AlertTriangle, not_applicable: AlertTriangle, failed: X };
// The status card only has passed / incomplete / failed styles.
const TONE_CLASS = { passed: "passed", completed: "passed", incomplete: "incomplete", not_applicable: "incomplete", failed: "failed" };

export function ResultPanel({
  result,
  onSave,
  saving,
  savedVersion,
  savedRevision,
  onCreateFoundation,
  projectId,
}: {
  result: CalculationResult;
  onSave: () => void;
  saving: boolean;
  savedVersion: ProjectVersion | null;
  savedRevision: SavedRevision | null;
  onCreateFoundation?: () => void;
  projectId?: number;
}) {
  const evidence = evidenceStatus(result);
  const ToneIcon = TONE_ICON[evidence.tone];
  const governing = result.checks.find((item) => item.name === result.governing_check);
  const sortedChecks = useMemo(
    () => [...result.checks].sort((a, b) => b.utilization - a.utilization),
    [result.checks],
  );
  const finalProjectId = savedRevision?.project_id ?? savedVersion?.project_id ?? projectId;
  const [resultView, setResultView] = useState<"overview" | "details">("overview");
  const diagram = result.diagrams[0];
  return (
    <section className="result-section" id="result-panel">
      <header className="result-header">
        <div className={`result-status ${TONE_CLASS[evidence.tone]}`}>
          <ToneIcon size={24} />
          <span>
            <small>控制结论 · {evidence.qualifier}</small>
            <strong>当前输入与适用范围内{evidence.label}</strong>
          </span>
        </div>
        <div className="result-summary">
          <span>
            <small>控制验算</small>
            <strong>{result.governing_check}</strong>
          </span>
          <span>
            <small>最大利用率</small>
            <strong>{((governing?.utilization ?? 0) * 100).toFixed(1)}%</strong>
          </span>
          <span>
            <small>引擎版本</small>
            <strong>{result.engine_version}</strong>
          </span>
        </div>
        <div className="report-actions">
          {onCreateFoundation && (
            <button className="secondary-button" onClick={onCreateFoundation}>
              <ArrowRight size={17} />
              用反力创建独立基础
            </button>
          )}
          <button className="secondary-button" onClick={onSave} disabled={saving}>
            <Save size={17} />
            {savedRevision
              ? `已保存 R${savedRevision.revision_number}`
              : savedVersion
                ? `已保存 V${savedVersion.version_number}`
                : "保存版本"}
          </button>
          {savedRevision && finalProjectId ? (
            <a
              className="primary-button compact"
              href={`/api/v2/projects/${finalProjectId}/revisions/${savedRevision.id}/report.pdf`}
            >
              <Download size={17} /> 项目链 PDF
            </a>
          ) : savedVersion && finalProjectId ? (
            <a
              className="primary-button compact"
              href={`/api/v2/projects/${finalProjectId}/versions/${savedVersion.id}/report.pdf`}
            >
              <Download size={17} /> PDF 报告
            </a>
          ) : null}
        </div>
      </header>
      <div className="result-tabs" role="tablist" aria-label="结果显示层级">
        {(["overview", "details"] as const).map((view) => (
          <button
            key={view}
            role="tab"
            aria-selected={resultView === view}
            className={resultView === view ? "active" : ""}
            onClick={() => setResultView(view)}
          >
            {view === "overview" ? "速览" : "详细计算"}
          </button>
        ))}
      </div>

      <div className="result-grid">
        <section className="panel checks-panel">
          <PanelHeader number="03" title="验算结果" subtitle="Checks ranked by utilization" />
          <div className="check-list">
            {sortedChecks.map((check) => (
              <article className="check-item" key={check.name}>
                <div className="check-title">
                  <span className={check.passed ? "check-ok" : "check-fail"}>
                    {check.passed ? <Check size={15} /> : <X size={15} />}
                  </span>
                  <strong>{check.name}</strong>
                  <span>{(check.utilization * 100).toFixed(1)}%</span>
                </div>
                <div className="utilization-track">
                  <span
                    style={{ width: `${Math.min(check.utilization * 100, 100)}%` }}
                    className={check.passed ? "" : "over"}
                  />
                </div>
                <div className="check-values">
                  <span>
                    需求 {check.demand.value.toFixed(3)} {check.demand.unit}
                  </span>
                  <span>
                    能力/限值 {check.capacity.value.toFixed(3)} {check.capacity.unit}
                  </span>
                </div>
                <small>{check.reference}</small>
                {check.note && <p>{check.note}</p>}
              </article>
            ))}
          </div>
        </section>

        {resultView === "details" ? (
          <section className="panel transparent-panel">
            <PanelHeader number="04" title="过程与图形" subtitle="Transparent calculation" />
            {diagram ? <DiagramChart series={diagram} /> : <NoDiagram text="该模块当前以验算步骤为主" />}
            <div className="step-list">
              {result.steps.map((step, index) => (
                <details key={`${step.name}-${index}`} open={index === 0}>
                  <summary>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{step.name}</strong>
                    <small>
                      {step.result.value.toFixed(4)} {step.result.unit}
                    </small>
                  </summary>
                  <div>
                    <code>{step.equation}</code>
                    <p>{step.substitution}</p>
                    <small>{step.reference}</small>
                  </div>
                </details>
              ))}
            </div>
          </section>
        ) : (
          <section className="panel transparent-panel overview-panel">
            <PanelHeader number="04" title="控制信息" subtitle="At-a-glance" />
            {diagram ? <DiagramChart series={diagram} /> : <NoDiagram text="切换“详细计算”查看公式与条文" />}
            <div className="scope-summary">
              <strong>适用范围</strong>
              {result.applicability.map((item) => (
                <span key={item}>{item}</span>
              ))}
              {result.catalog_versions &&
                Object.entries(result.catalog_versions).map(([key, value]) => (
                  <small key={key}>
                    {key} · {value}
                  </small>
                ))}
            </div>
          </section>
        )}
      </div>

      {resultView === "details" && (
        <div className="combination-strip">
          {result.combinations.map((combination) => (
            <article key={combination.name}>
              <span>{combination.limit_state}</span>
              <strong>{combination.name}</strong>
              <small>
                {combination.total.value.toFixed(3)} {combination.total.unit}
              </small>
            </article>
          ))}
        </div>
      )}

      {result.warnings.length > 0 && (
        <div className="warning-list">
          {result.warnings.map((warning) => (
            <div className={`warning ${warning.severity}`} key={warning.code}>
              <AlertTriangle size={17} />
              <span>{warning.message}</span>
            </div>
          ))}
        </div>
      )}

      <footer className="result-footer">
        <small>Trace ID · {result.trace_id}</small>
      </footer>
    </section>
  );
}

function NoDiagram({ text }: { text: string }) {
  return (
    <div className="no-diagram">
      <Gauge size={30} />
      <span>{text}</span>
    </div>
  );
}

export function DiagramChart({ series }: { series: CalculationResult["diagrams"][0] }) {
  const width = 520;
  const height = 190;
  const padding = 30;
  const xs = series.points.map((point) => point.x.value);
  const ys = series.points.map((point) => point.value.value);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const maxAbsY = Math.max(...ys.map(Math.abs), 1e-9);
  const coordinates = series.points.map((point) => ({
    x: padding + ((point.x.value - minX) / Math.max(maxX - minX, 1e-9)) * (width - 2 * padding),
    y: height / 2 - (point.value.value / maxAbsY) * (height / 2 - padding),
  }));
  return (
    <div className="diagram-chart">
      <div>
        <strong>{series.name}</strong>
        <small>{series.points[0]?.value.unit}</small>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`}>
        <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} />
        <polyline points={coordinates.map(({ x, y }) => `${x},${y}`).join(" ")} />
        {coordinates.map(({ x, y }, index) => (
          <circle cx={x} cy={y} r="3" key={index} />
        ))}
      </svg>
    </div>
  );
}
