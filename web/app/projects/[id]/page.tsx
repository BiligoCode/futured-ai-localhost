"use client";

import { useParams } from "next/navigation";

import { Stepper } from "@/components/Stepper";
import { useProject } from "@/lib/useProject";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { project, error } = useProject(id);

  if (error && !project) return <p className="rounded-lg bg-red-50 p-4 text-red-700">{error}</p>;
  if (!project) return <p className="text-slate-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <Stepper current={project.stage === "storyboard" ? 2 : 3} />
      <div>
        <h1 className="text-2xl font-semibold">{project.title}</h1>
        <p className="text-slate-600">{project.concept}</p>
      </div>
      <ol className="list-decimal space-y-1 pl-6">
        {project.scenes.map((s) => (
          <li key={s.id}>{s.title}</li>
        ))}
      </ol>
    </div>
  );
}
