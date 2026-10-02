/** The heading every dashboard page opens with: title, one line of context, and the page's main action. */
export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="max-w-2xl min-w-0">
        <h1 className="font-serif text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">{title}</h1>
        {subtitle && <p className="mt-2 text-lg text-muted">{subtitle}</p>}
      </div>
      {children && <div className="flex min-w-0 flex-wrap gap-2">{children}</div>}
    </div>
  );
}
