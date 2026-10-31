"use client";

import { useEffect, useRef } from "react";
import type { DesignStage, GroundwaterCondition, SnowExposure } from "@/lib/scene-model";
import type { FoundationDesignSpecification, MemberSpecification, Mode, SceneLoadCase } from "@/lib/types";

/**
 * Browser-local draft of a legacy scene, keyed by scene family. The keys
 * match drafts written by earlier versions so existing drafts still load.
 */
export type LocalSceneDraft = {
  variantId?: string;
  mode?: Mode;
  material?: string;
  parameters?: Record<string, unknown>;
  loadCases?: SceneLoadCase[];
  foundationType?: string;
  bearingCapacity?: number | "";
  groundwaterCondition?: GroundwaterCondition;
  waterTableDepth?: number | "";
  groundwaterSource?: string;
  snowExposure?: SnowExposure;
  snowExemptionReason?: string;
  optionalWindEnabled?: boolean;
  /** Legacy local draft compatibility. */
  groundwaterKnown?: boolean;
  sceneTitle?: string;
  selectedProject?: number | "new";
  designStage?: DesignStage;
  memberSpecifications?: MemberSpecification[];
  foundationSpecifications?: FoundationDesignSpecification[];
};

function storageKey(familyId: string) {
  return `steel-compass:scene-draft:${familyId}`;
}

function readLocalSceneDraft(familyId: string): LocalSceneDraft | null {
  let saved: string | null = null;
  try {
    saved = window.localStorage.getItem(storageKey(familyId));
    return saved ? (JSON.parse(saved) as LocalSceneDraft) : null;
  } catch {
    // A corrupt draft is dropped so it cannot block the workspace again.
    if (saved !== null) {
      try {
        window.localStorage.removeItem(storageKey(familyId));
      } catch {
        // Storage unavailable; nothing to clean up.
      }
    }
    return null;
  }
}

/**
 * Restores the local draft whenever the scene family changes and saves the
 * current draft after every later change. The first save after a restore is
 * skipped so the restored values are not immediately overwritten by the
 * render that triggered the restore.
 */
export function useLocalSceneDraft(
  familyId: string,
  draft: LocalSceneDraft,
  restore: (draft: LocalSceneDraft | null) => void,
) {
  const hydrated = useRef(false);
  const restoreRef = useRef(restore);
  useEffect(() => {
    restoreRef.current = restore;
  });
  useEffect(() => {
    hydrated.current = false;
    restoreRef.current(readLocalSceneDraft(familyId));
  }, [familyId]);
  const serialized = JSON.stringify(draft);
  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      return;
    }
    try {
      window.localStorage.setItem(storageKey(familyId), serialized);
    } catch {
      // Storage full or blocked: the server draft remains the durable copy.
    }
  }, [familyId, serialized]);
}
