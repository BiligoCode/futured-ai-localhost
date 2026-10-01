"use client";

import { useCallback, useSyncExternalStore } from "react";

export const SPLIT_KEY = "lara-deck-split";
export const DEFAULT_RATIO = 0.6;
const MIN = 0.3;
const MAX = 0.75;

export function clampRatio(r: number): number {
  return Math.min(MAX, Math.max(MIN, r));
}

export function readRatio(raw: string | null): number {
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) ? clampRatio(n) : DEFAULT_RATIO;
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

const getSnapshot = () => window.localStorage.getItem(SPLIT_KEY);
const getServerSnapshot = () => null;

/** The editor pane's share of the workspace width, remembered across visits. */
export function useDeckSplit(): [number, (r: number) => void] {
  const ratio = readRatio(useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot));
  const setRatio = useCallback((r: number) => {
    window.localStorage.setItem(SPLIT_KEY, clampRatio(r).toFixed(3));
    listeners.forEach((l) => l());
  }, []);
  return [ratio, setRatio];
}
