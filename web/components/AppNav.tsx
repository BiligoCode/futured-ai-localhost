"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "@/components/Icon";
import { useI18n } from "@/lib/i18n";

type Section = "overview" | "animations" | "slides" | "assessments";

const ITEMS: { section: Section; href: string; icon: IconName }[] = [
  { section: "overview", href: "/", icon: "grid" },
  { section: "animations", href: "/animations", icon: "film" },
  { section: "slides", href: "/slides", icon: "slides" },
  { section: "assessments", href: "/assessments", icon: "exam" },
];

/** Which section a page belongs to: animations live under /projects, decks under /decks. */
export function sectionOf(path: string): Section | null {
  if (path === "/") return "overview";
  if (path.startsWith("/animations") || path.startsWith("/projects") || path.startsWith("/new/animation")) return "animations";
  if (path.startsWith("/slides") || path.startsWith("/decks") || path.startsWith("/new/slides")) return "slides";
  if (path.startsWith("/assessments") || path.startsWith("/new/assessment")) return "assessments";
  return null;
}

/** Full-width workspaces keep the sidebar as a narrow rail of icons. */
const isWorkspace = (path: string) => /^\/decks\/[^/]+/.test(path) || /^\/assessments\/[^/]+\/(students|compare)\//.test(path);

function NavList({ path, rail, onNavigate }: { path: string; rail: boolean; onNavigate?: () => void }) {
  const { t } = useI18n();
  const current = sectionOf(path);
  return (
    <ul className="space-y-1">
      {ITEMS.map((item) => {
        const active = current === item.section;
        const label = t.nav[item.section];
        return (
          <li key={item.section}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              title={rail ? label : undefined}
              aria-label={rail ? label : undefined}
              className={
                "group relative flex items-center gap-3 rounded-lg py-2 text-sm font-medium transition-colors " +
                (rail ? "justify-center px-0" : "px-3") +
                (active ? " bg-surface text-ink shadow-[0_1px_2px_rgb(15_20_27/0.08)] ring-1 ring-rule" : " text-muted hover:bg-sunken hover:text-ink")
              }
            >
              {active && <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-full bg-accent" aria-hidden="true" />}
              <Icon name={item.icon} size={18} className={active ? "text-accent" : "text-faint group-hover:text-ink"} />
              {!rail && <span className="truncate">{label}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** The sidebar (≥ lg). */
export function AppNav() {
  const { t } = useI18n();
  const path = usePathname() ?? "/";
  const rail = isWorkspace(path);
  return (
    <nav
      aria-label={t.nav.label}
      className={`sticky top-[calc(3.5rem+1px)] hidden h-[calc(100dvh-3.5rem-1px)] shrink-0 overflow-y-auto border-r border-rule bg-paper py-5 lg:block ${rail ? "w-16 px-2" : "w-56 px-3"}`}
    >
      <NavList path={path} rail={rail} />
    </nav>
  );
}

/** The same sections behind a menu button (< lg); the header keeps its height. */
export function MobileNav() {
  const { t } = useI18n();
  const path = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onClick(e: MouseEvent) {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div ref={box} className="relative lg:hidden">
      <button type="button" className="btn-icon" aria-expanded={open} aria-label={t.nav.menu} onClick={() => setOpen((o) => !o)}>
        <Icon name={open ? "close" : "menu"} />
      </button>
      {open && (
        <nav aria-label={t.nav.label} className="absolute top-full left-0 z-40 mt-2 w-64 rounded-xl border border-rule bg-paper p-2 shadow-lg">
          <NavList path={path} rail={false} onNavigate={() => setOpen(false)} />
        </nav>
      )}
    </div>
  );
}
