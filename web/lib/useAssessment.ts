"use client";

import { useCallback, useEffect, useState } from "react";

import { getAssessment } from "./api";
import type { Assessment } from "./types";

const POLL_MS = 2000;

/** An assessment, polled while papers are being read or graded, the rubric drafted or the class analysed. */
export function useAssessment(id: string) {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setAssessment(await getAssessment(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    getAssessment(id)
      .then((a) => !cancelled && setAssessment(a))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const busy = assessment?.stats.busy ?? false;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [busy, refresh]);

  return { assessment, error, refresh, setAssessment };
}

/** The order the professor last looked at the papers in, so the paper page can step through the same list. */
export function rememberOrder(assessmentId: string, ids: string[]) {
  try {
    sessionStorage.setItem(`lara-order-${assessmentId}`, JSON.stringify(ids));
  } catch {
    /* private mode: the default order is used */
  }
}

export function recallOrder(assessmentId: string): string[] | null {
  try {
    const raw = sessionStorage.getItem(`lara-order-${assessmentId}`);
    const ids = raw ? JSON.parse(raw) : null;
    return Array.isArray(ids) ? ids.map(String) : null;
  } catch {
    return null;
  }
}
