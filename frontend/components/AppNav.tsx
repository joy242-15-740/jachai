"use client";

import { FileText, LayoutDashboard, ListChecks, type LucideIcon, ShieldCheck, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/queue", label: "Alert queue", icon: ListChecks },
  { href: "/simulator", label: "Simulator", icon: SlidersHorizontal },
  { href: "/notice", label: "Notice", icon: FileText },
  { href: "/trust", label: "Trust", icon: ShieldCheck },
];

export function AppNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Primary"
      className="flex items-center gap-1 overflow-x-auto rounded-full border border-border bg-surface p-1 text-sm"
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`) ||
          (href === "/queue" && (pathname.startsWith("/cases") || pathname.startsWith("/examples")));
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`flex shrink-0 items-center gap-2 rounded-full px-3.5 py-2 font-medium ${
              active ? "bg-primary text-white" : "text-muted hover:bg-canvas hover:text-navy"
            }`}
          >
            <Icon aria-hidden="true" className="h-4 w-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
