"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listProjects } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Your explanations</h1>
        <p className="text-slate-600">Animated, narrated explanations built from your own course material.</p>
      </div>

      {error && <p className="rounded-lg bg-red-50 p-4 text-red-700">{error}</p>}
      {!projects && !error && <p className="text-slate-500">Loading…</p>}

      {projects?.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="mb-4 text-slate-600">No explanations yet. Upload your lecture notes and pick a concept to start.</p>
          <Link href="/new" className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700">
            Create your first explanation
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects?.map((p) => {
          const status =
            p.stage === "storyboard"
              ? "Script draft"
              : p.preview.version === 0
                ? "Creating video…"
                : p.final.version > 0
                  ? "Narrated"
                  : "Ready to narrate";
          return (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-300 hover:shadow"
            >
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="rounded bg-slate-100 px-2 py-0.5 font-medium uppercase text-slate-600">{p.language}</span>
                <span className="text-slate-500">{status}</span>
              </div>
              <h2 className="font-semibold">{p.title}</h2>
              <p className="mt-1 line-clamp-2 text-sm text-slate-600">{p.concept}</p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
