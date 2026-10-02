import { ApiError, uploadPapers } from "./api";
import type { UploadResult } from "./types";

export const BATCH = 5;

export type UploadOutcome = { added: number; skipped: UploadResult["skipped"]; failed: File[]; error: string | null };

/** Upload papers a few at a time (progress, and one failed request does not lose the rest); each batch is retried once. */
export async function uploadInBatches(
  assessmentId: string,
  files: File[],
  splitEvery: number | null,
  onProgress: (done: number, total: number) => void,
): Promise<UploadOutcome> {
  const out: UploadOutcome = { added: 0, skipped: [], failed: [], error: null };
  onProgress(0, files.length);
  for (let i = 0; i < files.length; i += BATCH) {
    const batch = files.slice(i, i + BATCH);
    let result: UploadResult | null = null;
    for (let attempt = 0; attempt < 2 && !result; attempt++) {
      try {
        result = await uploadPapers(assessmentId, batch, splitEvery);
      } catch (e) {
        out.error = e instanceof Error ? e.message : String(e);
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) break; // the server refused it: retrying will not help
      }
    }
    if (result) {
      out.added += result.added.length;
      out.skipped.push(...result.skipped);
    } else {
      out.failed.push(...batch);
    }
    onProgress(Math.min(files.length, i + batch.length), files.length);
  }
  if (!out.failed.length) out.error = null;
  return out;
}

const ACCEPTED = /\.(pdf|jpe?g|png)$/i;

/** New files added to a list without duplicates (same name and size); anything that is not PDF/JPG/PNG is left out. */
export function mergeFiles(current: File[], picked: File[]): File[] {
  const seen = new Set(current.map((f) => `${f.name}|${f.size}`));
  const out = [...current];
  for (const f of picked) {
    const key = `${f.name}|${f.size}`;
    if (!seen.has(key) && (ACCEPTED.test(f.name) || ["application/pdf", "image/jpeg", "image/png"].includes(f.type))) {
      seen.add(key);
      out.push(f);
    }
  }
  return out;
}
