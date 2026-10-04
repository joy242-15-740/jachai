import type { SVGProps } from "react";

export type IconName = "queue" | "simulator" | "notice" | "trust" | "sun" | "moon";

export function LogoMark({ className = "h-10 w-10" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="jachai-mark" x1="7" y1="4" x2="42" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor="#51E4C7" />
          <stop offset="0.52" stopColor="#12AF98" />
          <stop offset="1" stopColor="#087F6B" />
        </linearGradient>
        <linearGradient id="jachai-shine" x1="11" y1="8" x2="35" y2="39" gradientUnits="userSpaceOnUse">
          <stop stopColor="white" stopOpacity="0.92" />
          <stop offset="1" stopColor="white" stopOpacity="0.64" />
        </linearGradient>
      </defs>
      <rect x="3" y="3" width="42" height="42" rx="14" fill="url(#jachai-mark)" />
      <path d="M13 23.5L20.2 30.5L35.5 15.5" stroke="url(#jachai-shine)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M34.5 27.5V34.5H27.5" stroke="white" strokeOpacity="0.42" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="35" cy="35" r="2" fill="white" fillOpacity="0.88" />
    </svg>
  );
}

export function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  const common: SVGProps<SVGSVGElement> = {
    "aria-hidden": true,
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
  if (name === "queue") {
    return (
      <svg {...common}>
        <path d="M5 5.5h14M5 12h9M5 18.5h6" />
        <circle cx="18" cy="12" r="2.25" />
        <path d="m19.7 13.7 1.8 1.8" />
      </svg>
    );
  }
  if (name === "simulator") {
    return (
      <svg {...common}>
        <path d="M4 19V9M10 19V5M16 19v-7M22 19V3" />
        <path d="M2.5 19h20" />
      </svg>
    );
  }
  if (name === "notice") {
    return (
      <svg {...common}>
        <path d="M6.5 4.5h8l3 3v12H6.5z" />
        <path d="M14.5 4.5v3h3M9 11h6M9 14.5h4" />
        <path d="m8.5 18 1.4 1.4 2.6-3" />
      </svg>
    );
  }
  if (name === "trust") {
    return (
      <svg {...common}>
        <path d="M12 3.5 19 6v5.2c0 4.3-2.8 7.4-7 9.3-4.2-1.9-7-5-7-9.3V6z" />
        <path d="m8.8 12 2.1 2.1 4.4-4.6" />
      </svg>
    );
  }
  if (name === "sun") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3.5" />
        <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M20 15.3A8.4 8.4 0 0 1 8.7 4a8.5 8.5 0 1 0 11.3 11.3Z" />
    </svg>
  );
}

