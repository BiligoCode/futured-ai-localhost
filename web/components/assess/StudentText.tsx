/** A student's words as Lara transcribed them: ~~crossed out~~ shown struck through, [?] (unreadable) marked. */
export function StudentText({ text, className = "" }: { text: string; className?: string }) {
  const parts = text.split(/(~~[\s\S]*?~~|\[\?\])/g).filter(Boolean);
  return (
    <span className={`whitespace-pre-wrap break-words ${className}`}>
      {parts.map((p, i) =>
        p.startsWith("~~") && p.endsWith("~~") && p.length > 4 ? (
          <del key={i} className="text-muted decoration-critical/70">
            {p.slice(2, -2)}
          </del>
        ) : p === "[?]" ? (
          <mark key={i} className="rounded bg-warn-soft px-0.5 text-gold-ink">
            [?]
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </span>
  );
}
