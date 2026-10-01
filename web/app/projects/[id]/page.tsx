"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/Icon";

import { Stepper } from "@/components/Stepper";
import { StoryboardEditor } from "@/components/StoryboardEditor";
import { VideoWorkspace } from "@/components/VideoWorkspace";
import { deleteProject, reopenScript } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { isBusy, useProject } from "@/lib/useProject";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const router = useRouter();
  const { project, error, setProject } = useProject(id);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [scriptDirty, setScriptDirty] = useState(false);
  const [goingBack, setGoingBack] = useState(false);

  function backToSetup() {
    if (scriptDirty && !window.confirm(t.discardChanges)) return;
    router.push(`/new?from=${id}`);
  }

  async function backToScript() {
    if (!project || (isBusy(project) && !window.confirm(t.confirmBackToScript))) return;
    setGoingBack(true);
    setDeleteError(null);
    try {
      setProject(await reopenScript(project.id));
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setGoingBack(false);
    }
  }

  async function onDelete() {
    if (!project || !window.confirm(t.confirmDelete(project.title))) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteProject(project.id);
      router.push("/");
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  }

  if (error && !project)
    return (
      <p className="notice notice-error" role="alert">
        {error}
      </p>
    );
  if (!project)
    return (
      <p className="text-muted" aria-live="polite">
        {t.loading}
      </p>
    );

  const step = project.stage === "storyboard" ? 2 : project.preview.version === 0 ? 3 : 4;

  return (
    <div className="space-y-8">
      <Stepper current={step} go={step === 2 ? { 1: backToSetup } : { 1: backToSetup, 2: backToScript }} />
      <div className="flex items-start justify-between gap-4">
        <div className="max-w-3xl min-w-0">
          <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight break-words">{project.title}</h1>
          <p className="mt-2 text-lg text-muted break-words">{project.concept}</p>
        </div>
        <div className="mt-1 flex shrink-0 flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={project.stage === "storyboard" ? backToSetup : backToScript}
            disabled={goingBack}
            className="btn btn-secondary"
          >
            <Icon name="back" size={16} />
            {project.stage === "storyboard" ? t.backToSetup : t.backToScript}
          </button>
          <button type="button" onClick={onDelete} disabled={deleting} className="btn btn-ghost">
            <Icon name="trash" size={16} />
            {t.deleteVideo}
          </button>
        </div>
      </div>
      {deleteError && (
        <p className="notice notice-error" role="alert">
          {deleteError}
        </p>
      )}

      {project.stage === "storyboard" ? (
        <StoryboardEditor key={project.id} project={project} onChange={setProject} onDirty={setScriptDirty} />
      ) : (
        <VideoWorkspace project={project} onChange={setProject} />
      )}
    </div>
  );
}
