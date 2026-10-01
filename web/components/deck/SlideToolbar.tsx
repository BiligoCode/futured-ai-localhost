"use client";

import { type Editor, useEditorState } from "@tiptap/react";

import { Icon, type IconName } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";
import { BODY_PX, PALETTE, SIZES } from "@/lib/slideHtml";

type Block = "title" | "heading" | "body";

function ToolButton({ icon, label, active, disabled, onClick }: {
  icon: IconName;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()} // keep the editor's selection
      onClick={onClick}
      className={`btn-icon ${active ? "bg-accent-soft !text-accent" : ""}`}
    >
      <Icon name={icon} size={18} />
    </button>
  );
}

function Divider() {
  return <span className="mx-1 h-5 w-px bg-rule" aria-hidden="true" />;
}

/** Formatting controls for the active slide's editor; disabled when no slide has focus. */
export function SlideToolbar({ editor }: { editor: Editor | null }) {
  const { t } = useI18n();
  const state = useEditorState({
    editor,
    selector: ({ editor }) =>
      editor
        ? {
            block: (editor.isActive("heading", { level: 1 }) ? "title" : editor.isActive("heading", { level: 2 }) ? "heading" : "body") as Block,
            bold: editor.isActive("bold"),
            italic: editor.isActive("italic"),
            underline: editor.isActive("underline"),
            highlight: editor.isActive("highlight"),
            bullets: editor.isActive("bulletList"),
            numbers: editor.isActive("orderedList"),
            align: (["left", "center", "right"] as const).find((a) => editor.isActive({ textAlign: a })) ?? "left",
            color: (editor.getAttributes("textStyle").color as string | undefined) ?? null,
            size: (editor.getAttributes("textStyle").fontSize as string | undefined) ?? null,
            canUndo: editor.can().undo(),
            canRedo: editor.can().redo(),
          }
        : null,
  });
  const off = !editor;
  const run = (fn: (chain: ReturnType<Editor["chain"]>) => boolean) => {
    if (editor) fn(editor.chain().focus());
  };
  const sizePx = state?.size ? parseInt(state.size, 10) : BODY_PX;

  return (
    <div
      role="toolbar"
      aria-label={t.tb.toolbar}
      className="flex flex-wrap items-center gap-0.5 rounded-lg border border-rule bg-surface px-2 py-1.5 shadow-[0_1px_2px_rgb(15_20_27/0.06)]"
    >
      <select
        aria-label={t.tb.style}
        disabled={off}
        value={state?.block ?? "body"}
        onMouseDown={(e) => e.stopPropagation()}
        onChange={(e) => {
          const v = e.target.value as Block;
          run((c) => (v === "title" ? c.setHeading({ level: 1 }) : v === "heading" ? c.setHeading({ level: 2 }) : c.setParagraph()).run());
        }}
        className="field mr-1 w-auto py-1 text-sm"
      >
        <option value="title">{t.tb.title}</option>
        <option value="heading">{t.tb.heading}</option>
        <option value="body">{t.tb.body}</option>
      </select>

      <ToolButton icon="bold" label={t.tb.bold} active={state?.bold} disabled={off} onClick={() => run((c) => c.toggleBold().run())} />
      <ToolButton icon="italic" label={t.tb.italic} active={state?.italic} disabled={off} onClick={() => run((c) => c.toggleItalic().run())} />
      <ToolButton icon="underline" label={t.tb.underline} active={state?.underline} disabled={off} onClick={() => run((c) => c.toggleUnderline().run())} />
      <ToolButton icon="highlight" label={t.tb.highlight} active={state?.highlight} disabled={off} onClick={() => run((c) => c.toggleHighlight().run())} />
      <Divider />

      <div className="flex items-center gap-0.5" role="group" aria-label={t.tb.size}>
        {SIZES.map((s) => (
          <button
            key={s.px}
            type="button"
            disabled={off}
            aria-pressed={sizePx === s.px}
            title={`${t.tb.size} ${s.label}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => run((c) => (s.px === BODY_PX ? c.unsetFontSize() : c.setFontSize(`${s.px}px`)).run())}
            className={`btn-icon w-auto px-1.5 text-xs font-semibold ${sizePx === s.px ? "bg-accent-soft !text-accent" : ""}`}
          >
            {s.label}
          </button>
        ))}
      </div>
      <Divider />

      <div className="flex items-center gap-1 px-1" role="group" aria-label={t.tb.color}>
        <button
          type="button"
          disabled={off}
          aria-label={t.tb.defaultColor}
          title={t.tb.defaultColor}
          aria-pressed={!state?.color}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => run((c) => c.unsetColor().run())}
          className={`grid h-5 w-5 place-items-center rounded-full border border-rule-strong bg-surface text-[10px] text-muted ${!state?.color ? "ring-2 ring-accent ring-offset-1" : ""}`}
        >
          A
        </button>
        {PALETTE.map((c) => (
          <button
            key={c.hex}
            type="button"
            disabled={off}
            aria-label={`${t.tb.color}: ${t.colorNames[c.name] ?? c.name}`}
            title={t.colorNames[c.name] ?? c.name}
            aria-pressed={state?.color === c.hex}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => run((ch) => ch.setColor(c.hex).run())}
            style={{ background: c.hex }}
            className={`h-5 w-5 rounded-full ${state?.color === c.hex ? "ring-2 ring-accent ring-offset-1" : ""}`}
          />
        ))}
      </div>
      <Divider />

      <ToolButton icon="bullets" label={t.tb.bullets} active={state?.bullets} disabled={off} onClick={() => run((c) => c.toggleBulletList().run())} />
      <ToolButton icon="numbers" label={t.tb.numbers} active={state?.numbers} disabled={off} onClick={() => run((c) => c.toggleOrderedList().run())} />
      <Divider />
      <ToolButton icon="alignLeft" label={t.tb.alignLeft} active={state?.align === "left"} disabled={off} onClick={() => run((c) => c.setTextAlign("left").run())} />
      <ToolButton icon="alignCenter" label={t.tb.alignCenter} active={state?.align === "center"} disabled={off} onClick={() => run((c) => c.setTextAlign("center").run())} />
      <ToolButton icon="alignRight" label={t.tb.alignRight} active={state?.align === "right"} disabled={off} onClick={() => run((c) => c.setTextAlign("right").run())} />
      <Divider />
      <ToolButton icon="undo" label={t.tb.undo} disabled={off || !state?.canUndo} onClick={() => run((c) => c.undo().run())} />
      <ToolButton icon="redo" label={t.tb.redo} disabled={off || !state?.canRedo} onClick={() => run((c) => c.redo().run())} />
    </div>
  );
}
