"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/queue", label: "Alert queue" },
  { href: "/simulator", label: "Policy simulator" },
  { href: "/notice", label: "Merchant notice" },
  { href: "/trust", label: "Trust" },
];

export function AppNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 overflow-x-auto rounded-full border border-line bg-panel/50 p-1 text-sm shadow-sm backdrop-blur-xl">
      {NAV.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`shrink-0 rounded-full px-3.5 py-2 font-medium ${
              active ? "bg-ink text-page shadow-sm" : "text-muted hover:bg-panel hover:text-ink"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
