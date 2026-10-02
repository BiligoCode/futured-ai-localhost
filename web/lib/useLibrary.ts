"use client";

import { useCallback, useEffect, useState } from "react";

import { listAssessments, listDecks, listProjects } from "./api";
import type { AssessmentSummary, DeckSummary, Project } from "./types";

export type Library = {
  projects: Project[] | null;
  decks: DeckSummary[] | null;
  assessments: AssessmentSummary[] | null;
};

type Part = keyof Library;
const POLL_MS = 4000;

async function fetchLibrary(want: Set<string>): Promise<Library> {
  const [projects, decks, assessments] = await Promise.all([
    want.has("projects") ? listProjects() : Promise.resolve(null),
    want.has("decks") ? listDecks() : Promise.resolve(null),
    want.has("assessments") ? listAssessments() : Promise.resolve(null),
  ]);
  return { projects, decks, assessments };
}

/** Everything the dashboard lists. Polls while anything is still being made or graded. */
export function useLibrary(parts: Part[] = ["projects", "decks", "assessments"]) {
  const [lib, setLib] = useState<Library>({ projects: null, decks: null, assessments: null });
  const [error, setError] = useState<string | null>(null);
  const key = parts.join(",");

  const reload = useCallback(() => {
    return fetchLibrary(new Set(key.split(",")))
      .then((l) => {
        setLib(l);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [key]);

  useEffect(() => {
    let cancelled = false;
    fetchLibrary(new Set(key.split(",")))
      .then((l) => !cancelled && setLib(l))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [key]);

  const busy =
    (lib.assessments ?? []).some((a) => a.busy) || (lib.projects ?? []).some((p) => p.stage === "scenes" && p.preview.version === 0);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void reload(), POLL_MS);
    return () => clearInterval(timer);
  }, [busy, reload]);

  return { ...lib, error, setLib, reload };
}
