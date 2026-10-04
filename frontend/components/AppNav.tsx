"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/BrandIcons";

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/queue", label: "Alert queue", icon: "queue" },
  { href: "/simulator", label: "Policy simulator", icon: "simulator" },
  { href: "/notice", label: "Merchant notice", icon: "notice" },
  { href: "/trust", label: "Trust", icon: "trust" },
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
            className={`flex shrink-0 items-center gap-2 rounded-full px-3.5 py-2 font-medium ${
              active ? "bg-ink text-page shadow-sm" : "text-muted hover:bg-panel hover:text-ink"
            }`}
          >
            <Icon name={item.icon} className="h-4 w-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
