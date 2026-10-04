import "@fontsource/noto-sans-bengali/400.css";
import "@fontsource/noto-sans-bengali/600.css";
import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import type { ReactNode } from "react";
import { AppNav } from "@/components/AppNav";
import { LogoMark } from "@/components/BrandIcons";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Jachai",
  description: "Merchant-transaction integrity for Bangla QR (synthetic demo)",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-50 border-b border-line bg-page/65 backdrop-blur-2xl">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 lg:px-8">
            <Link href="/" className="group flex shrink-0 items-center gap-3">
              <LogoMark className="h-10 w-10 drop-shadow-lg transition-transform group-hover:-rotate-3 group-hover:scale-105" />
              <span>
                <span className="block text-[15px] font-semibold leading-4 tracking-tight">Jachai</span>
                <span className="bangla block text-[10px] leading-4 text-muted">যাচাই · review with context</span>
              </span>
            </Link>
            <div className="flex min-w-0 items-center gap-2">
              <AppNav />
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="enter mx-auto min-h-[calc(100vh-11rem)] max-w-7xl px-5 py-8 lg:px-8 lg:py-10">
          {children}
        </main>
        <footer className="mx-auto flex max-w-7xl flex-col gap-2 px-5 pb-8 pt-3 text-xs text-muted sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <span>Synthetic data only · No real customer information</span>
          <span>Recommendation, not verdict · Every action needs a human</span>
        </footer>
        <Script id="jachai-theme-bootstrap" strategy="beforeInteractive">
          {`(function(){try{var t=localStorage.getItem('jachai-theme');if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='light'}})();`}
        </Script>
      </body>
    </html>
  );
}
