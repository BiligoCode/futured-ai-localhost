"use client";

import Highlight from "@tiptap/extension-highlight";
import TextAlign from "@tiptap/extension-text-align";
import { Color, FontSize, TextStyle } from "@tiptap/extension-text-style";
import { type Editor, EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import type { AnimationRef, Slide } from "@/lib/types";

import { SlideFrame } from "./SlideFrame";
import { VideoBlock } from "./VideoBlock";

export const SELECTION_CHARS = 500;

/** The schema equals the API whitelist: h1/h2, paragraphs, lists, bold/italic/underline, highlight, colour, size, alignment. */
export function slideExtensions() {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2] },
      strike: false,
      code: false,
      codeBlock: false,
      blockquote: false,
      horizontalRule: false,
      link: false,
    }),
    TextStyle,
    Color,
    FontSize,
    Highlight,
    TextAlign.configure({ types: ["heading", "paragraph"] }),
  ];
}

/** One slide, editable. Reports its HTML on every change; takes external HTML (AI edits, undo) when it differs. */
export function SlideEditor({ slide, index, total, deckId, deckTitle, active, animation, onChange, onFocus, onSelection, onRemoveVideo, editorRef }: {
  slide: Slide;
  index: number;
  total: number;
  deckId: string;
  deckTitle: string;
  active: boolean;
  animation: AnimationRef | undefined;
  onChange: (html: string) => void;
  onFocus: (slideId: string) => void;
  onSelection: (text: string | null) => void;
  onRemoveVideo: () => void;
  editorRef: (slideId: string, editor: Editor | null) => void;
}) {
  const { t } = useI18n();
  const handlers = useRef({ onChange, onFocus, onSelection });
  useEffect(() => {
    handlers.current = { onChange, onFocus, onSelection };
  }, [onChange, onFocus, onSelection]);
  const textRef = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);

  const editor = useEditor({
    immediatelyRender: false,
    shouldRerenderOnTransaction: false,
    extensions: slideExtensions(),
    content: slide.html,
    editorProps: { attributes: { "aria-label": t.slideN(index + 1) } },
    onUpdate: ({ editor }) => handlers.current.onChange(editor.getHTML()),
    onFocus: () => handlers.current.onFocus(slide.id),
    onSelectionUpdate: ({ editor }) => {
      const { from, to } = editor.state.selection;
      const text = editor.state.doc.textBetween(from, to, " ").trim().slice(0, SELECTION_CHARS);
      handlers.current.onSelection(text || null);
    },
  });

  useEffect(() => {
    if (editor && slide.html !== editor.getHTML()) editor.commands.setContent(slide.html, { emitUpdate: false });
  }, [editor, slide.html]);

  useEffect(() => {
    editorRef(slide.id, editor);
    return () => editorRef(slide.id, null);
  }, [editor, slide.id, editorRef]);

  const check = useCallback(() => {
    const el = textRef.current;
    if (el) setOverflow(el.scrollHeight > el.clientHeight + 1);
  }, []);

  useEffect(() => {
    check();
    const el = textRef.current;
    if (!el) return;
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [check, slide.html, slide.video]);

  return (
    <div className="space-y-1.5">
      <SlideFrame
        className={`slide-editor shadow-[0_1px_2px_rgb(15_20_27/0.08),0_12px_32px_-18px_rgb(15_20_27/0.35)] ring-1 transition-[box-shadow,--tw-ring-color] ${
          active ? "ring-2 ring-accent" : "ring-rule"
        }`}
        textRef={textRef}
        overflow={overflow}
        footerLeft={deckTitle}
        footerRight={`${index + 1} / ${total}`}
        video={slide.video ? <VideoBlock animation={animation} deckId={deckId} onRemove={onRemoveVideo} /> : undefined}
      >
        <EditorContent editor={editor} className="h-full" />
      </SlideFrame>
      {overflow && (
        <p className="flex items-center gap-1.5 text-xs text-danger-ink" role="status">
          <span className="h-1.5 w-1.5 rounded-full bg-rec" aria-hidden="true" />
          {t.overflowHint}
        </p>
      )}
    </div>
  );
}
