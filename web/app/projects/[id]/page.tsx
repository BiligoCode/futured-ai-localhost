"use client";

import { useParams } from "next/navigation";

import { Stepper } from "@/components/Stepper";
import { StoryboardEditor } from "@/components/StoryboardEditor";
import { VideoWorkspace } from "@/components/VideoWorkspace";
import { useProject } from "@/lib/useProject";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { project, error, setProject } = useProject(id);

  if (error && !project)
    return (
      <p className="notice notice-error" role="alert">
        {error}
      </p>
    );
  if (!project)
    return (
      <p className="text-muted" aria-live="polite">
        Loading…
      </p>
    );

  const step = project.stage === "storyboard" ? 2 : project.preview.version === 0 ? 3 : 4;

  return (
    <div className="space-y-8">
      <Stepper current={step} />
      <div className="max-w-3xl">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight break-words">{project.title}</h1>
        <p className="mt-2 text-lg text-muted break-words">{project.concept}</p>
      </div>

      {project.stage === "storyboard" ? (
        <StoryboardEditor key={project.id} project={project} onChange={setProject} />
      ) : (
        <VideoWorkspace project={project} onChange={setProject} />
      )}
    </div>
  );
}
