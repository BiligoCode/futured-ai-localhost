"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { ProjectTile } from "@/components/ProjectTile";
import { deleteProject } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Project } from "@/lib/types";
import { useLibrary } from "@/lib/useLibrary";

export default function Animations() {
  const { t } = useI18n();
  const { projects, error, setLib } = useLibrary(["projects"]);
  const [actionError, setActionError] = useState<string | null>(null);
  const deleting = useRef(new Set<string>());

  async function onDelete(p: Project) {
    if (deleting.current.has(p.id) || !window.confirm(t.confirmDelete(p.title))) return;
    deleting.current.add(p.id);
    setActionError(null);
    try {
      await deleteProject(p.id);
      setLib((l) => ({ ...l, projects: l.projects?.filter((x) => x.id !== p.id) ?? null }));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      deleting.current.delete(p.id);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader title={t.nav.animations} subtitle={t.animationsSubtitle}>
        <Link href="/new/animation" className="btn btn-primary">
          <Icon name="plus" size={16} />
          {t.newAnimation}
        </Link>
      </PageHeader>
      {(error || actionError) && (
        <p className="notice notice-error" role="alert">
          {error ? t.loadError(error) : actionError}
        </p>
      )}
      {!projects && !error && (
        <p className="text-muted" aria-live="polite">
          {t.loading}
        </p>
      )}
      {projects?.length === 0 && <p className="text-muted">{t.noAnimations}</p>}
      {projects && projects.length > 0 && (
        <ul className="grid grid-cols-1 gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <ProjectTile key={p.id} p={p} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </div>
  );
}
