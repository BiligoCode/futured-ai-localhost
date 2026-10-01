import type { Metadata, Viewport } from "next";
import { Commissioner, STIX_Two_Text } from "next/font/google";
import { cookies } from "next/headers";
import Link from "next/link";

import { Mark } from "@/components/Stage";
import { I18nProvider, LanguageSwitch } from "@/lib/i18n";
import { LANG_COOKIE, MESSAGES, parseLang } from "@/lib/messages";

import "./globals.css";

const commissioner = Commissioner({ variable: "--font-commissioner", subsets: ["latin", "greek"] });
const stix = STIX_Two_Text({ variable: "--font-stix", subsets: ["latin", "greek"], style: ["normal", "italic"] });

async function uiLang() {
  return parseLang((await cookies()).get(LANG_COOKIE)?.value);
}

export async function generateMetadata(): Promise<Metadata> {
  const t = MESSAGES[await uiLang()];
  return { title: `Lara — ${t.tagline}`, description: t.dashSubtitle };
}

export const viewport: Viewport = {
  themeColor: "#f2f4f6",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const lang = await uiLang();
  const t = MESSAGES[lang];
  return (
    <html lang={lang} className={`${commissioner.variable} ${stix.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <I18nProvider initial={lang}>
          <a
            href="#main"
            className="sr-only rounded-md bg-ink px-3 py-2 text-sm text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
          >
            {t.skipToContent}
          </a>
          <header className="border-b border-rule bg-paper/90 backdrop-blur supports-[backdrop-filter]:bg-paper/75">
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
              <Link href="/" className="group flex items-center gap-3 rounded-md" translate="no">
                <Mark className="h-8 w-8" />
                <span className="font-serif text-2xl leading-none font-semibold tracking-tight">Lara</span>
                <span className="hidden border-l border-rule pl-3 text-sm text-muted md:inline">{t.tagline}</span>
              </Link>
              <div className="flex items-center gap-3">
                <Link href="/new" className="btn btn-primary">
                  {t.newExplanation}
                </Link>
                <LanguageSwitch />
              </div>
            </div>
          </header>
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
            {children}
          </main>
        </I18nProvider>
      </body>
    </html>
  );
}
