// Single source for how a calculation result's evidence level is worded.
// A screening result is never shown as a plain pass, and a result that is not
// independently verified always carries that qualifier.

export type EvidenceTone = "passed" | "failed" | "incomplete" | "completed";

export interface EvidenceInput {
  mode?: string | null;
  result_class?: string | null;
  status?: string | null;
  quick_outcome?: "screening_passed" | "screening_failed" | null;
  engineering_status?: "passed" | "failed" | "incomplete" | null;
  workflow_status?: string | null;
  verification_status?: string | null;
}

export interface EvidenceStatus {
  tone: EvidenceTone;
  /** Conclusion wording; always names screening or professional checking. */
  label: string;
  /** Evidence level, e.g. "方案筛查 · 未独立验证". */
  qualifier: string;
  /** Label plus the unverified marker when applicable. */
  headline: string;
  screening: boolean;
  verified: boolean;
}

const SCREENING_CLASSES = new Set(["quick_estimate", "scheme_estimate"]);

const LABELS: Record<"screening" | "professional", Record<EvidenceTone, string>> = {
  screening: { passed: "筛查通过", failed: "筛查不通过", incomplete: "资料不完整", completed: "筛查已完成" },
  professional: { passed: "专业校核通过", failed: "专业校核不通过", incomplete: "专业校核待补齐", completed: "专业校核待补齐" },
};

function screeningTone(input: EvidenceInput): EvidenceTone {
  if (input.workflow_status === "failed") return "failed";
  if (input.status === "not_applicable" || input.status === "incomplete") return "incomplete";
  // quick_outcome is authoritative when the backend sends it; null means the
  // screening produced no conclusion (missing inputs or capability limits).
  if (input.quick_outcome !== undefined) {
    if (input.quick_outcome === "screening_failed") return "failed";
    if (input.quick_outcome === "screening_passed") return "passed";
    return "incomplete";
  }
  if (input.status === "failed") return "failed";
  if (input.status === "passed") return "passed";
  if (input.status) return "incomplete";
  // Only a workflow state is known: every check ran, but no outcome was sent.
  return input.workflow_status === "ready" ? "completed" : "incomplete";
}

export function evidenceStatus(input: EvidenceInput): EvidenceStatus {
  // Scene revisions run in quick mode but report their evidence class
  // separately, so result_class wins over mode when present.
  const screening = input.result_class
    ? SCREENING_CLASSES.has(input.result_class)
    : input.mode !== "professional";
  const verified = input.verification_status === "independently_verified";

  let tone: EvidenceTone;
  if (screening) {
    tone = screeningTone(input);
  } else {
    const engineering = input.engineering_status ?? input.status;
    if (engineering === "failed" || input.workflow_status === "failed") tone = "failed";
    // An unverified method or an unfinished workflow cannot form a professional pass.
    else if (engineering === "passed" && verified && (!input.workflow_status || input.workflow_status === "ready")) tone = "passed";
    else tone = "incomplete";
  }

  const label = LABELS[screening ? "screening" : "professional"][tone];
  return {
    tone,
    label,
    qualifier: `${screening ? "方案筛查" : "专业校核"}${verified ? "" : " · 未独立验证"}`,
    headline: verified ? label : `${label} · 未独立验证`,
    screening,
    verified,
  };
}

const CHECK_STATUS_LABELS: Record<string, string> = {
  ready: "已完成计算",
  complete: "已完成计算",
  incomplete: "尚未完成",
  failed: "筛查不通过",
  pass: "筛查通过",
  passed: "筛查通过",
  not_calculated: "未计算",
  capability_unavailable: "超出当前能力",
};

/** Wording for one screening check group or item (members, connections, foundations). */
export function checkStatusLabel(value?: string | null): string {
  return CHECK_STATUS_LABELS[value ?? ""] ?? value ?? "未计算";
}
