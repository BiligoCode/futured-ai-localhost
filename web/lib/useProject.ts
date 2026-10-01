"use client";

import { useCallback, useEffect, useState } from "react";

import { getProject } from "./api";
import type { Project } from "./types";

const POLL_MS = 2000;
const BUSY_RENDER = new Set(["generating", "rendering", "repairing"]);

export function isBusy(project: Project | null): boolean {
  return !!project?.scenes.some((s) => BUSY_RENDER.has(s.render_status) || s.audio_status === "generating");
}

export function useProject(id: string) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProject(await getProject(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    getProject(id)
      .then((p) => !cancelled && setProject(p))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const busy = isBusy(project);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [busy, refresh]);

  return { project, error, refresh, setProject };
}
