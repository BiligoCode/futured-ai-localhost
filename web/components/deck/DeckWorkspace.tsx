"use client";

import type { Editor } from "@tiptap/react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import { ApiError, chatDeck, deleteDeck, getDeck, saveDeck, saveDeckOnLeave } from "@/lib/api";
import { mergeChatResult, undoChatEdits } from "@/lib/deckMerge";
import { useI18n } from "@/lib/i18n";
import { slideTitle } from "@/lib/slideHtml";
import type { AnimationRef, ChatMessage, Deck, EditLog, Slide } from "@/lib/types";
import { useDeckSplit } from "@/lib/useDeckSplit";

import { AnimationsMenu } from "./AnimationsMenu";
import { DeckChat } from "./DeckChat";
import { ExportMenu } from "./ExportMenu";
import { SlideEditor } from "./SlideEditor";
import { SlideStrip } from "./SlideStrip";
import { SlideToolbar } from "./SlideToolbar";

export const AUTOSAVE_MS = 800;
const UNDO_TOAST_MS = 6000;

type SaveState = "saved" | "dirty" | "saving" | "error";

export type DeckDoc = {
  title: string;
  slides: Slide[];
  version: number;
  animations: AnimationRef[];
  chat: ChatMessage[];
};

export function newSlideId(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 8);
}

function fromDeck(deck: Deck): DeckDoc {
  return { title: deck.title, slides: deck.slides, version: deck.version, animations: deck.animations, chat: deck.chat };
}

export function DeckWorkspace({ deck }: { deck: Deck }) {
  const { t } = useI18n();
  const router = useRouter();
  const [doc, setDoc] = useState<DeckDoc>(() => fromDeck(deck));
  const [wantedActive, setActiveId] = useState<string | null>(deck.slides[0]?.id ?? null);
  const [selection, setSelection] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [notice, setNotice] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [removed, setRemoved] = useState<{ slide: Slide; index: number } | null>(null);
  const [editors, setEditors] = useState<Map<string, Editor>>(() => new Map());
  const editorsRef = useRef(editors);
  const [chatBusy, setChatBusy] = useState(false);
  const [undo, setUndo] = useState<{ snapshot: Slide[]; edits: EditLog[] } | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null); // a freshly added slide takes the cursor
  const [ratio, setRatio] = useDeckSplit();
  const panes = useRef<HTMLDivElement>(null);

  // `latest` is updated synchronously by `update` (not in an effect), so a save that starts inside an async
  // chain always reads the current document. `changes` counts local edits; a save that finishes with new
  // changes behind it saves again at once.
  const latest = useRef(doc);
  const unsaved = useRef(false);
  const changes = useRef(0);
  const dirtySlides = useRef(new Set<string>()); // slides typed in since the last successful save
  const saving = useRef<Promise<void> | null>(null);
  useEffect(() => {
    unsaved.current = saveState !== "saved";
  }, [saveState]);
  useEffect(() => {
    editorsRef.current = editors;
  }, [editors]);

  const update = useCallback((fn: (d: DeckDoc) => DeckDoc) => {
    latest.current = fn(latest.current);
    setDoc(latest.current);
  }, []);

  const change = useCallback((fn: (d: DeckDoc) => DeckDoc) => {
    changes.current += 1;
    update(fn);
    setSaveState("dirty");
  }, [update]);

  /** One PUT. Returns whether saving may continue (false after an error, which waits for Retry). */
  const attemptSave = useCallback(async (): Promise<boolean> => {
    const seq = changes.current;
    const d = latest.current;
    setSaveState("saving");
    try {
      const res = await saveDeck(deck.id, {
        title: d.title,
        slides: d.slides.map((s) => ({ id: s.id, html: s.html, video: s.video })),
        version: d.version,
      });
      // A chat reply may have advanced the version meanwhile: never go backwards.
      update((prev) => ({ ...prev, version: Math.max(prev.version, res.version), animations: res.animations }));
      if (changes.current === seq) dirtySlides.current.clear(); // typed during the save → stays dirty until a quiet save
      setSaveState(changes.current === seq ? "saved" : "dirty");
      setNotice(null);
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // Another tab (or a chat reply) saved first: take the server's deck but keep what was typed here since
        // the last save, then save again.
        try {
          const fresh = await getDeck(deck.id);
          const typed = new Map(latest.current.slides.filter((s) => dirtySlides.current.has(s.id)).map((s) => [s.id, s.html]));
          changes.current += 1;
          update(() => ({
            ...fromDeck(fresh),
            slides: fresh.slides.map((s) => (typed.has(s.id) ? { ...s, html: typed.get(s.id)! } : s)),
          }));
          setSaveState(typed.size ? "dirty" : "saved");
          setNotice(t.reloadedNotice);
          return typed.size > 0;
        } catch (err) {
          setSaveState("error");
          setNotice(err instanceof Error ? err.message : String(err));
          return false;
        }
      }
      setSaveState("error");
      setNotice(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, [deck.id, t.reloadedNotice, update]);

  /** Save now, and keep saving while edits keep arriving behind the save in flight. */
  const saveNow = useCallback((): Promise<void> => {
    if (saving.current) return saving.current;
    const task = (async () => {
      try {
        for (;;) {
          const seq = changes.current;
          if (!(await attemptSave()) || changes.current === seq) break;
        }
      } finally {
        saving.current = null;
      }
    })();
    saving.current = task;
    return task;
  }, [attemptSave]);

  useEffect(() => {
    if (saveState !== "dirty") return;
    const timer = setTimeout(() => void saveNow(), AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [saveState, doc, saveNow]);

  const flushSave = useCallback(async () => {
    if (saving.current) await saving.current;
    if (unsaved.current) await saveNow();
  }, [saveNow]);

  useEffect(() => {
    if (saveState === "saved") return;
    const guard = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [saveState]);

  // Leaving through a link or closing the tab must not lose the last keystrokes: send what is unsaved anyway.
  useEffect(() => {
    const leave = () => {
      if (!unsaved.current) return;
      const d = latest.current;
      saveDeckOnLeave(deck.id, { title: d.title, slides: d.slides.map((s) => ({ id: s.id, html: s.html, video: s.video })), version: d.version });
    };
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      leave();
    };
  }, [deck.id]);

  // --- slides -----------------------------------------------------------------------------------------------------

  const setSlideHtml = useCallback((id: string, html: string) => {
    dirtySlides.current.add(id);
    change((d) => ({ ...d, slides: d.slides.map((s) => (s.id === id ? { ...s, html } : s)) }));
  }, [change]);

  const registerEditor = useCallback((id: string, editor: Editor | null) => {
    setEditors((prev) => {
      if ((prev.get(id) ?? null) === editor) return prev;
      const next = new Map(prev);
      if (editor) next.set(id, editor);
      else next.delete(id);
      return next;
    });
  }, []);

  const jumpTo = useCallback((id: string, focus = false) => {
    if (!latest.current.slides.some((s) => s.id === id)) return;
    setActiveId(id);
    document.getElementById(`slide-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (focus) editorsRef.current.get(id)?.commands.focus("end");
  }, []);

  useEffect(() => {
    // Back from "Add to slides" (#slide-<id>): show the slide that just received the animation.
    const match = /^#slide-([0-9a-f]{8})$/.exec(window.location.hash);
    if (!match) return;
    history.replaceState(null, "", window.location.pathname);
    setTimeout(() => jumpTo(match[1]), 150);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, for the deck this page opened with
  }, []);

  function addSlide() {
    const slide: Slide = { id: newSlideId(), html: "", video: null };
    const at = activeId ? doc.slides.findIndex((s) => s.id === activeId) + 1 : doc.slides.length;
    change((d) => ({ ...d, slides: [...d.slides.slice(0, at), slide, ...d.slides.slice(at)] }));
    setActiveId(slide.id);
    setFocusId(slide.id); // the new editor focuses itself when it mounts
    setTimeout(() => document.getElementById(`slide-${slide.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  function moveSlide(from: number, to: number) {
    change((d) => {
      const slides = [...d.slides];
      const [s] = slides.splice(from, 1);
      slides.splice(to, 0, s);
      return { ...d, slides };
    });
  }

  function deleteSlide(index: number) {
    const slide = doc.slides[index];
    if (!slide || doc.slides.length === 1) return;
    change((d) => ({ ...d, slides: d.slides.filter((s) => s.id !== slide.id) }));
    if (activeId === slide.id) setActiveId(doc.slides[index === 0 ? 1 : index - 1]?.id ?? null);
    setRemoved({ slide, index });
  }

  useEffect(() => {
    if (!removed) return;
    const timer = setTimeout(() => setRemoved(null), UNDO_TOAST_MS);
    return () => clearTimeout(timer);
  }, [removed]);

  function undoDelete() {
    if (!removed) return;
    const { slide, index } = removed;
    change((d) => ({ ...d, slides: [...d.slides.slice(0, index), slide, ...d.slides.slice(index)] }));
    setRemoved(null);
    setTimeout(() => jumpTo(slide.id), 50);
  }

  function removeVideo(id: string) {
    change((d) => ({ ...d, slides: d.slides.map((s) => (s.id === id ? { ...s, video: null } : s)) }));
  }

  // --- chat -------------------------------------------------------------------------------------------------------

  async function sendChat(message: string, useSlide: boolean, useSelection: boolean, signal: AbortSignal) {
    setChatBusy(true);
    try {
      await flushSave();
      const baseline = latest.current.slides.map((s) => s.id); // what the server has when the request leaves
      const result = await chatDeck(
        deck.id,
        { message, slide_id: useSlide ? activeId : null, selection: useSelection ? selection : null },
        signal,
      );
      const snapshot = latest.current.slides;
      changes.current += 1;
      update((d) => ({
        ...d,
        slides: mergeChatResult(d.slides, result, baseline),
        version: Math.max(d.version, result.deck.version),
        animations: result.deck.animations,
        chat: result.deck.chat,
      }));
      setUndo(result.edits.length ? { snapshot, edits: result.edits } : null);
      // Local edits made while waiting still need saving; the merge kept them.
      setSaveState((s) => (s === "saved" ? "saved" : "dirty"));
      const first = result.edits.find((e) => e.op !== "delete");
      if (first) setTimeout(() => jumpTo(first.slide_id), 50);
    } finally {
      setChatBusy(false);
    }
  }

  function undoChat() {
    if (!undo) return;
    const { snapshot, edits } = undo;
    change((d) => ({ ...d, slides: undoChatEdits(d.slides, snapshot, edits) }));
    setUndo(null);
  }

  // --- header -----------------------------------------------------------------------------------------------------

  function commitTitle(value: string) {
    const title = value.trim();
    setEditingTitle(false);
    if (title && title !== doc.title) change((d) => ({ ...d, title }));
  }

  async function onDelete() {
    const linked = doc.animations.filter((a) => a.status !== "missing").length;
    if (!window.confirm(t.confirmDeleteDeck(doc.title, linked))) return;
    try {
      await deleteDeck(deck.id);
      changes.current = 0;
      setSaveState("saved");
      router.push("/");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }

  async function createAnimation() {
    await flushSave();
    router.push(`/new/animation?deck=${deck.id}`);
  }

  // --- divider ----------------------------------------------------------------------------------------------------

  function onDividerPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!(e.buttons & 1) || !panes.current) return;
    const r = panes.current.getBoundingClientRect();
    setRatio((e.clientX - r.left) / r.width);
  }

  // The active slide must exist: after the AI (or an undo) removes it, fall back to the first slide.
  const activeId = wantedActive && doc.slides.some((s) => s.id === wantedActive) ? wantedActive : (doc.slides[0]?.id ?? null);
  const animations = useMemo(() => new Map(doc.animations.map((a) => [a.project_id, a])), [doc.animations]);
  const labelOf = (id: string) => {
    const i = doc.slides.findIndex((s) => s.id === id);
    return i >= 0 ? slideTitle(doc.slides[i].html) || t.slideN(i + 1) : t.slideN(0);
  };
  const activeSlide = activeId ? { id: activeId, label: t.slideN(doc.slides.findIndex((s) => s.id === activeId) + 1) } : null;
  const activeEditor = activeId ? (editors.get(activeId) ?? null) : null;
  const linkedCount = doc.animations.filter((a) => a.status !== "missing").length;
  const saveLabel = saveState === "saving" ? t.saving : saveState === "saved" ? t.saved : saveState === "dirty" ? t.unsaved : t.saveFailedShort;

  return (
    <div className="-mx-4 -my-8 flex h-[calc(100dvh-3.5rem-1px)] flex-col sm:-mx-6 sm:-my-10">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule bg-paper px-4 py-3 sm:px-6">
        <div className="min-w-0 flex-1">
          {editingTitle ? (
            <input
              autoFocus
              defaultValue={doc.title}
              aria-label={t.editTitle}
              className="field max-w-xl font-serif text-2xl leading-tight font-semibold"
              onBlur={(e) => commitTitle(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitTitle(e.currentTarget.value);
                if (e.key === "Escape") setEditingTitle(false);
              }}
            />
          ) : (
            <button
              type="button"
              onClick={() => setEditingTitle(true)}
              title={t.editTitle}
              className="max-w-full truncate rounded-md px-1 -mx-1 text-left font-serif text-2xl leading-tight font-semibold hover:bg-sunken"
            >
              {doc.title}
            </button>
          )}
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-sm text-muted">
            <span className="inline-flex items-center gap-1">
              {t.slideCount(doc.slides.length)} ·
              <AnimationsMenu animations={doc.animations} label={t.animationCount(linkedCount)} />
            </span>
            <span aria-live="polite" className={`flex items-center gap-1.5 ${saveState === "error" ? "text-danger-ink" : ""}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${saveState === "saved" ? "bg-manim" : saveState === "error" ? "bg-rec" : "bg-gold pulse-soft"}`} aria-hidden="true" />
              {saveLabel}
              {saveState === "error" && (
                <button type="button" onClick={() => void saveNow()} className="font-semibold underline underline-offset-2">
                  {t.retry}
                </button>
              )}
            </span>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <button type="button" onClick={() => void createAnimation()} className="btn btn-secondary">
            <Icon name="film" size={16} />
            {t.createAnimation}
          </button>
          <ExportMenu
            deckId={deck.id}
            hasAnimations={doc.slides.some((s) => s.video && animations.get(s.video)?.status === "ready")}
            onBeforeExport={flushSave}
            onError={setNotice}
          />
          <button type="button" onClick={() => void onDelete()} className="btn btn-ghost" title={t.deleteDeck}>
            <Icon name="trash" size={16} />
            <span className="sr-only sm:not-sr-only">{t.deleteDeck}</span>
          </button>
        </div>
        {notice && (
          <p className="notice notice-warn basis-full" role="status">
            {notice}
          </p>
        )}
      </header>

      <div ref={panes} className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section
          className="flex min-h-[60dvh] min-w-0 flex-col lg:min-h-0 lg:flex-none"
          style={{ flexBasis: `${ratio * 100}%` }}
          aria-label={t.editorLabel}
        >
          <div className="flex min-h-0 flex-1">
            <SlideStrip
              slides={doc.slides}
              activeId={activeId}
              onSelect={(id) => {
                if (id !== activeId) setSelection(null);
                jumpTo(id);
              }}
              onMove={moveSlide}
              onAdd={addSlide}
              onDelete={deleteSlide}
              className="hidden w-52 shrink-0 border-r border-rule bg-paper sm:flex"
            />
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="border-b border-rule bg-paper px-3 py-2">
                <SlideToolbar editor={activeEditor} />
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto bg-sunken/60 px-4 py-6 sm:px-8">
                <div className="mx-auto max-w-[960px] space-y-8">
                  {doc.slides.map((s, i) => (
                    <div key={s.id} id={`slide-${s.id}`} className="scroll-mt-4" onPointerDown={() => setActiveId(s.id)}>
                      <SlideEditor
                        slide={s}
                        index={i}
                        total={doc.slides.length}
                        deckId={deck.id}
                        deckTitle={doc.title}
                        active={s.id === activeId}
                        animation={s.video ? animations.get(s.video) : undefined}
                        onChange={(html) => setSlideHtml(s.id, html)}
                        autoFocus={s.id === focusId}
                        onFocus={(id) => {
                          if (id !== activeId) setSelection(null);
                          setActiveId(id);
                        }}
                        onBlur={() => void flushSave()}
                        onSelection={setSelection}
                        onRemoveVideo={() => removeVideo(s.id)}
                        editorRef={registerEditor}
                      />
                    </div>
                  ))}
                  <div className="sm:hidden">
                    <button type="button" onClick={addSlide} className="btn btn-secondary w-full">
                      <Icon name="plus" size={16} />
                      {t.addSlide}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t.resizePanes}
          aria-valuenow={Math.round(ratio * 100)}
          aria-valuemin={30}
          aria-valuemax={75}
          tabIndex={0}
          onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
          onPointerMove={onDividerPointerMove}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setRatio(ratio - 0.02);
            if (e.key === "ArrowRight") setRatio(ratio + 0.02);
          }}
          className="hidden w-2 shrink-0 cursor-col-resize bg-rule transition-colors hover:bg-accent focus-visible:bg-accent lg:block"
        />

        <aside className="flex min-h-[40dvh] min-w-0 flex-1 flex-col border-t border-rule bg-surface lg:min-h-0 lg:border-t-0" aria-label={t.askLara}>
          <DeckChat
            messages={doc.chat}
            activeSlide={activeSlide}
            selection={selection}
            busy={chatBusy}
            canUndo={undo !== null}
            onSend={sendChat}
            onUndo={undoChat}
            onClearSelection={() => setSelection(null)}
            onJump={(id) => jumpTo(id)}
            slideLabel={labelOf}
          />
        </aside>
      </div>

      {removed && (
        <div role="status" className="fixed bottom-5 left-1/2 z-20 flex -translate-x-1/2 items-center gap-3 rounded-lg bg-ink px-4 py-2.5 text-sm text-white shadow-lg">
          {t.slideRemoved(slideTitle(removed.slide.html) || t.slideN(removed.index + 1))}
          <button type="button" onClick={undoDelete} className="font-semibold text-manim underline underline-offset-2">
            {t.undo}
          </button>
        </div>
      )}
    </div>
  );
}
