"use client";

import { Fragment } from "react";
import { BarChart3, ClipboardCheck, Save, TriangleAlert } from "lucide-react";
import type { WorkbenchModel } from "@/components/pergola/workbench-model";
import { checkStatusLabel } from "@/lib/evidence-status";
import { analysisEvidence } from "@/lib/pergola-project";

type ItemStatus = string | undefined;

function itemTone(status: ItemStatus) {
  return status === "failed" ? "fail" : status === "complete" || status === "pass" ? "pass" : "warning";
}

export function ResultsPanel({ model }: { model: WorkbenchModel }) {
  const { mode, project, handleSelection } = model;
  const result = project.analysisResult;
  if (!result) {
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>计算闭环状态</strong>
            <small>保存模型后由服务端生成荷载、组合与快照</small>
          </div>
          <BarChart3 size={18} />
        </div>
        <div className="qa-result-summary">
          <span>当前状态</span>
          <strong>尚未分析</strong>
          <span>模型版本</span>
          <strong>Geometry 2.3</strong>
          <span>专业验证</span>
          <strong className="warning">unverified</strong>
        </div>
        {mode === "project" && (
          <button type="button" className="qa-secondary-action" disabled={project.serverBusy} onClick={project.analyze}>
            <BarChart3 size={16} />
            {project.serverBusy ? "分析中…" : "保存并开始完整分析"}
          </button>
        )}
      </>
    );
  }
  const evidence = analysisEvidence(result.workflow_status);
  const memberItems = [...(result.member_checks?.items ?? [])].sort((a, b) => (b.utilization ?? -1) - (a.utilization ?? -1));
  const failedMembers = memberItems.filter((item) => item.status === "failed");
  const incompleteMembers = memberItems.filter((item) => item.status !== "pass" && item.status !== "failed");
  const incompleteConnections = result.connection_checks.items.filter((item) => item.status !== "complete" && item.status !== "failed");
  const balanceChecks = result.structural_analysis.balance_checks;
  const summary: Array<[string, string, boolean?]> = [
    ["工作流", evidence.headline, evidence.tone !== "completed"],
    ["结构分析", checkStatusLabel(result.structural_analysis.status)],
    ["构件验算", checkStatusLabel(result.member_checks?.status ?? "incomplete")],
    ["连接验算", checkStatusLabel(result.connection_checks.status)],
    ["基础与地基", checkStatusLabel(result.foundation_checks.status)],
    ["最低屈曲系数", result.buckling_analysis?.factors?.[0]?.toFixed(3) ?? "未计算"],
  ];
  const { selectedProjectId, sceneInstanceId, analysisSnapshotId } = project;
  return (
    <>
      <div className="qa-panel-title">
        <div>
          <strong>计算闭环结果</strong>
          <small>结果来自不可变 Schema 4.0 分析快照 · {evidence.qualifier}</small>
        </div>
        <BarChart3 size={18} />
      </div>
      <div className="qa-result-summary">
        {summary.map(([label, value, warning]) => (
          <Fragment key={label}>
            <span>{label}</span>
            <strong className={warning ? "warning" : ""}>{value}</strong>
          </Fragment>
        ))}
      </div>
      <div className="qa-task-list">
        <span className={balanceChecks.length > 0 && balanceChecks.every((item) => item.balanced) ? "done" : ""}>
          <ClipboardCheck size={15} />
          逐工况荷载与反力平衡
        </span>
        <span
          className={
            memberItems.length > 0 && failedMembers.length === 0 && incompleteMembers.length === 0 && result.member_checks?.status === "complete"
              ? "done"
              : ""
          }
        >
          <TriangleAlert size={15} />
          失败构件 {failedMembers.length} 根 · 未完成 {incompleteMembers.length} 根
        </span>
        <span
          className={
            result.connection_checks.items.length > 0 && incompleteConnections.length === 0 && result.connection_checks.status === "complete"
              ? "done"
              : ""
          }
        >
          <TriangleAlert size={15} />
          未完成连接 {incompleteConnections.length} 个
        </span>
        {result.trace.unsupported_capabilities.map((item) => (
          <span key={item}>
            <TriangleAlert size={15} />
            {item}
          </span>
        ))}
      </div>
      <details className="qa-result-details" open>
        <summary>荷载与反力平衡</summary>
        {balanceChecks.map((item) => (
          <div key={item.case} className={item.balanced ? "pass" : "fail"}>
            <strong>{item.case ?? "未编号组合"}</strong>
            <span>{item.balanced ? "平衡" : "不平衡"}</span>
            <small>{item.residual_kn?.map((value) => Number(value).toExponential(2)).join(" / ") ?? "无残差记录"} kN</small>
          </div>
        ))}
      </details>
      <details className="qa-result-details" open>
        <summary>构件验算与图面定位</summary>
        {memberItems.map((item) => (
          <button key={item.member_id} type="button" onClick={() => item.member_id && handleSelection({ kind: "member", id: item.member_id })}>
            <strong>{item.member_id ?? "未编号构件"}</strong>
            <span className={itemTone(item.status)}>{checkStatusLabel(item.status ?? "not_calculated")}</span>
            <small>
              利用率 {item.utilization == null ? "未计算" : item.utilization.toFixed(3)} · {item.controlling_case ?? "无控制组合"}
            </small>
            {item.reason && <small>{item.reason}</small>}
          </button>
        ))}
      </details>
      <details className="qa-result-details">
        <summary>连接、柱脚与锚栓</summary>
        {result.connection_checks.items.map((item) => (
          <button
            key={item.connection_id ?? item.mark}
            type="button"
            disabled={!item.node_id}
            onClick={() => item.node_id && handleSelection({ kind: "node", id: item.node_id })}
          >
            <strong>{item.mark ?? item.connection_id ?? "未编号连接"}</strong>
            <span className={itemTone(item.status)}>{checkStatusLabel(item.status ?? "not_calculated")}</span>
            <small>{item.failed_checks?.join("、") || item.issue_code || "已形成检查包"}</small>
          </button>
        ))}
      </details>
      <details className="qa-result-details">
        <summary>短柱、基础与地基</summary>
        {result.foundation_checks.items.map((item) => (
          <button
            key={item.foundation_id ?? item.mark}
            type="button"
            disabled={!item.foundation_id}
            onClick={() => item.foundation_id && handleSelection({ kind: "foundation", id: item.foundation_id })}
          >
            <strong>{item.mark ?? item.foundation_id ?? "未编号基础"}</strong>
            <span className={itemTone(item.status)}>{checkStatusLabel(item.status ?? "not_calculated")}</span>
            <small>{item.failed_checks?.join("、") || item.pending_checks?.join("、") || "已形成检查包"}</small>
          </button>
        ))}
      </details>
      <details className="qa-result-details">
        <summary>公式、版本与未支持范围</summary>
        {result.trace.formulas?.map((item) => (
          <div key={`${item.topic}-${item.source}`}>
            <strong>{item.topic ?? "计算主题"}</strong>
            <small>{item.source ?? "未记录来源"}</small>
          </div>
        ))}
        {result.trace.unsupported_capabilities.map((item) => (
          <div key={item} className="fail">
            <strong>未完成</strong>
            <small>{item}</small>
          </div>
        ))}
      </details>
      {mode === "project" && selectedProjectId !== null && sceneInstanceId !== null && analysisSnapshotId !== null && (
        <a
          className="qa-secondary-action"
          href={`/api/v2/projects/${selectedProjectId}/scene-instances/${sceneInstanceId}/analysis-snapshots/${analysisSnapshotId}/report.pdf`}
        >
          <Save size={16} />
          下载快照计算书 PDF
        </a>
      )}
    </>
  );
}
