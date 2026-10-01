import type { Metadata, Viewport } from "next";
import { Commissioner, STIX_Two_Text } from "next/font/google";
import Link from "next/link";

import { Mark } from "@/components/Stage";

import "./globals.css";

const commissioner = Commissioner({ variable: "--font-commissioner", subsets: ["latin", "greek"] });
const stix = STIX_Two_Text({ variable: "--font-stix", subsets: ["latin", "greek"], style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: "Lara — Learning Assessment & Resource Automation",
  description: "Turn your course material into a narrated animated explanation.",
};

export const viewport: Viewport = {
  themeColor: "#f2f4f6",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${commissioner.variable} ${stix.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only rounded-md bg-ink px-3 py-2 text-sm text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
        >
          Skip to content
        </a>
        <header className="border-b border-rule bg-paper/90 backdrop-blur supports-[backdrop-filter]:bg-paper/75">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <Link href="/" className="group flex items-center gap-3 rounded-md" translate="no">
              <Mark className="h-8 w-8" />
              <span className="font-serif text-2xl leading-none font-semibold tracking-tight">Lara</span>
              <span className="hidden border-l border-rule pl-3 text-sm text-muted md:inline">
                Learning Assessment &amp; Resource Automation
              </span>
            </Link>
            <Link href="/new" className="btn btn-primary">
              New explanation
            </Link>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
          {children}
        </main>
      </body>
    </html>
  );
}
