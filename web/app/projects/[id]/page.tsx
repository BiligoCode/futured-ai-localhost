"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { ScenesBoard } from "@/components/ScenesBoard";
import { Stepper } from "@/components/Stepper";
import { StoryboardEditor } from "@/components/StoryboardEditor";
import { useProject } from "@/lib/useProject";

type Tab = "scenes" | "voice";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { project, error, setProject } = useProject(id);
  const [tab, setTab] = useState<Tab>("scenes");

  if (error && !project) return <p className="rounded-lg bg-red-50 p-4 text-red-700">{error}</p>;
  if (!project) return <p className="text-slate-500">Loading…</p>;

  const step = project.stage === "storyboard" ? 2 : tab === "scenes" ? 3 : 4;

  return (
    <div className="space-y-6">
      <Stepper current={step} />
      <div>
        <h1 className="text-2xl font-semibold">{project.title}</h1>
        <p className="text-slate-600">{project.concept}</p>
      </div>

      {project.stage === "storyboard" ? (
        <StoryboardEditor key={project.id} project={project} onChange={setProject} />
      ) : (
        <>
          <div role="tablist" className="flex gap-1 border-b border-slate-200">
            {(["scenes", "voice"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={
                  "-mb-px border-b-2 px-4 py-2 text-sm font-medium " +
                  (tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800")
                }
              >
                {t === "scenes" ? "Scenes" : "Voice & Export"}
              </button>
            ))}
          </div>
          {tab === "scenes" ? (
            <ScenesBoard project={project} onChange={setProject} onContinue={() => setTab("voice")} />
          ) : (
            <p className="text-slate-500">Voice studio coming next.</p>
          )}
        </>
      )}
    </div>
  );
}
