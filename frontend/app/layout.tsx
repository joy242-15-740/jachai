import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/noto-sans-bengali/400.css";
import "@fontsource/noto-sans-bengali/600.css";
import "./globals.css";
import { Bell } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { AppNav } from "@/components/AppNav";
import { Logo } from "@/components/Brand";
import { JudgeWalkthrough } from "@/components/JudgeWalkthrough";

export const metadata: Metadata = {
  title: "Jachai",
  description: "AI-powered merchant risk & transaction integrity for Bangla QR (synthetic demo)",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-50 border-b border-border bg-canvas/85 backdrop-blur-xl">
          <div className="mx-auto grid max-w-7xl grid-cols-[auto_1fr] items-center gap-x-4 gap-y-3 px-5 py-3 lg:grid-cols-[1fr_auto_1fr] lg:px-8">
            <Link href="/" className="shrink-0" aria-label="Jachai dashboard">
              <Logo />
            </Link>
            <div className="col-span-2 flex min-w-0 justify-start lg:col-span-1 lg:justify-center">
              <AppNav />
            </div>
            <div className="col-start-2 row-start-1 flex items-center justify-end gap-2 lg:col-start-3">
              <Link
                href="/queue"
                aria-label="Open the alert queue"
                title="Alerts"
                className="relative grid h-10 w-10 place-items-center rounded-full border border-border bg-surface text-muted hover:text-primary"
              >
                <Bell aria-hidden="true" className="h-4 w-4" />
              </Link>
              <span
                className="flex h-10 items-center gap-2 rounded-full border border-border bg-surface py-1 pl-1 pr-3 text-xs font-medium text-navy"
                title="Demo session: no login in this phase"
              >
                <span className="grid h-8 w-8 place-items-center rounded-full bg-primary text-[13px] font-semibold text-white">
                  A
                </span>
                Analyst
              </span>
            </div>
          </div>
        </header>
        <main className="enter mx-auto min-h-[calc(100vh-11rem)] max-w-7xl px-5 py-7 lg:px-8 lg:py-9">
          {children}
        </main>
        <JudgeWalkthrough />
        <footer className="mx-auto flex max-w-7xl flex-col gap-2 border-t border-border px-5 pb-8 pt-5 text-xs text-muted sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <span>Synthetic data only · No real customer information</span>
          <span>Recommendation, not verdict · Every action needs a human</span>
        </footer>
      </body>
    </html>
  );
}
