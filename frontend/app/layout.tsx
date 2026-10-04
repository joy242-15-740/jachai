import "@fontsource/noto-sans-bengali/400.css";
import "@fontsource/noto-sans-bengali/600.css";
import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Jachai",
  description: "Merchant-transaction integrity for Bangla QR (synthetic demo)",
};

const NAV = [
  { href: "/queue", label: "Alert queue" },
  { href: "/simulator", label: "Policy simulator" },
  { href: "/notice", label: "Merchant notice" },
  { href: "/trust", label: "Trust" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-line bg-panel">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-semibold">Jachai</span>
              <span className="bangla text-sm text-muted">যাচাই</span>
            </Link>
            <nav className="flex flex-wrap gap-5 text-sm">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="text-muted hover:text-ink">
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-10 text-xs text-muted">
          Synthetic data only. Jachai recommends; a human analyst decides. Nothing is blocked
          automatically.
        </footer>
      </body>
    </html>
  );
}
