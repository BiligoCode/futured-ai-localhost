"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { LANG_COOKIE, MESSAGES, type Messages, type UiLang } from "./messages";

type I18n = { lang: UiLang; t: Messages; setLang: (lang: UiLang) => void };

const I18nContext = createContext<I18n | null>(null);

/** Provides the interface language. The server reads the same cookie, so the first paint is already right. */
export function I18nProvider({ initial, children }: { initial: UiLang; children: React.ReactNode }) {
  const router = useRouter();
  const [lang, setLangState] = useState<UiLang>(initial);

  const setLang = useCallback(
    (next: UiLang) => {
      document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
      setLangState(next);
      router.refresh(); // re-render server parts (header, page title) in the new language
    },
    [router],
  );

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return <I18nContext.Provider value={{ lang, t: MESSAGES[lang], setLang }}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** The EΛ / EN switch in the header. */
export function LanguageSwitch() {
  const { lang, t, setLang } = useI18n();
  return (
    <div role="group" aria-label={t.interfaceLanguage} className="flex rounded-lg bg-sunken p-0.5 text-xs font-semibold">
      {(["el", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={lang === l}
          onClick={() => lang !== l && setLang(l)}
          title={MESSAGES[l].langName[l]}
          className={
            "rounded-md px-2.5 py-1.5 transition-colors " +
            (lang === l ? "bg-surface text-ink shadow-[0_1px_2px_rgb(15_20_27/0.12)]" : "text-muted hover:text-ink")
          }
        >
          {l === "el" ? "ΕΛ" : "EN"}
        </button>
      ))}
    </div>
  );
}
