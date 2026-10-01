"use client";

import { useParams } from "next/navigation";

import { Stepper } from "@/components/Stepper";
import { StoryboardEditor } from "@/components/StoryboardEditor";
import { VideoWorkspace } from "@/components/VideoWorkspace";
import { useProject } from "@/lib/useProject";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { project, error, setProject } = useProject(id);

  if (error && !project) return <p className="rounded-lg bg-red-50 p-4 text-red-700">{error}</p>;
  if (!project) return <p className="text-slate-500">Loading…</p>;

  const step = project.stage === "storyboard" ? 2 : project.preview.version === 0 ? 3 : 4;

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
        <VideoWorkspace project={project} onChange={setProject} />
      )}
    </div>
  );
}
