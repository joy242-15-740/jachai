"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/BrandIcons";

type Theme = "light" | "dark";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("jachai-theme", next);
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
      className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-line bg-panel/50 text-muted shadow-sm backdrop-blur-xl hover:bg-panel hover:text-ink"
    >
      {theme === "dark" ? <Icon name="sun" /> : <Icon name="moon" />}
    </button>
  );
}

