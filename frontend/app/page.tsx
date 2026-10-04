import Link from "next/link";
import { Icon, type IconName } from "@/components/BrandIcons";
import { HomeInfographics } from "@/components/HomeInfographics";

const CARDS: {
  href: string;
  tag: string;
  title: string;
  text: string;
  icon: IconName;
  tone: string;
}[] = [
  {
    href: "/queue",
    tag: "Investigate",
    title: "Alert queue",
    text: "Review the highest-priority shops with evidence, context and neutral language.",
    icon: "queue",
    tone: "from-rose-400/20 to-orange-300/5 text-rose-400",
  },
  {
    href: "/simulator",
    tag: "Compare",
    title: "Policy simulator",
    text: "Replay five policy choices and see the trade-off between recovery and merchant harm.",
    icon: "simulator",
    tone: "from-sky-400/20 to-indigo-300/5 text-sky-400",
  },
  {
    href: "/notice",
    tag: "Communicate",
    title: "Merchant notice",
    text: "Preview respectful Bangla communication and give merchants a route to explain.",
    icon: "notice",
    tone: "from-emerald-400/20 to-teal-300/5 text-emerald-400",
  },
  {
    href: "/trust",
    tag: "Verify",
    title: "Trust center",
    text: "Inspect evidence status, fairness slices, limitations and validation boundaries.",
    icon: "trust",
    tone: "from-violet-400/20 to-fuchsia-300/5 text-violet-400",
  },
];

export default function Home() {
  return (
    <>
      <section className="hero-glow relative overflow-hidden rounded-[2rem] border border-line bg-panel/55 px-6 py-10 shadow-2xl shadow-slate-950/5 backdrop-blur-2xl sm:px-10 sm:py-14 lg:px-14 lg:py-16">
        <div className="soft-grid absolute inset-y-0 right-0 w-1/2 opacity-30 [mask-image:linear-gradient(to_left,black,transparent)]" />
        <div className="ambient-orb absolute -right-20 -top-28 h-72 w-72 rounded-full bg-accent/10 blur-3xl" />
        <div className="relative max-w-4xl">
          <div className="mb-6 flex flex-wrap gap-2">
            <span className="rounded-full border border-accent/20 bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">
              Merchant intelligence
            </span>
            <span className="rounded-full border border-line bg-panel/60 px-3 py-1 text-xs font-medium text-muted">
              Synthetic demo
            </span>
            <span className="rounded-full border border-line bg-panel/60 px-3 py-1 text-xs font-medium text-muted">
              Human-in-the-loop
            </span>
          </div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-[1.02] tracking-[-0.055em] sm:text-6xl lg:text-7xl">
            Protect honest shops.
            <span className="block bg-gradient-to-r from-accent via-teal-500 to-sky-500 bg-clip-text text-transparent">
              Review the right ones.
            </span>
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-muted sm:text-lg">
            Jachai combines payment, shop and network evidence to surface hidden cash-out
            patterns—then leaves every decision with an analyst.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/queue"
              className="rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-page shadow-lg shadow-slate-950/15 hover:-translate-y-0.5"
            >
              Open review queue
            </Link>
            <Link
              href="/simulator"
              className="rounded-full border border-line bg-panel/60 px-5 py-2.5 text-sm font-semibold hover:-translate-y-0.5 hover:bg-panel"
            >
              Explore policy impact
            </Link>
          </div>
        </div>
      </section>

      <HomeInfographics />

      <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CARDS.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="glass-panel group rounded-2xl p-5 hover:-translate-y-1 hover:border-accent/25"
          >
            <div
              className={`mb-8 grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br text-lg font-semibold ${card.tone}`}
            >
              <Icon name={card.icon} className="h-5 w-5" />
            </div>
            <div className="eyebrow">{card.tag}</div>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">{card.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted">{card.text}</p>
            <div className="mt-5 text-sm font-semibold text-accent opacity-0 transition-opacity group-hover:opacity-100">
              Open workspace →
            </div>
          </Link>
        ))}
      </section>

      <section className="glass-inset mt-6 flex flex-col gap-4 rounded-2xl px-5 py-4 text-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <span className="font-semibold">Evidence, not accusation.</span>
          <span className="ml-2 text-muted">
            Scores prioritize attention; they never determine guilt.
          </span>
        </div>
        <Link href="/trust" className="shrink-0 font-semibold text-accent hover:underline">
          See validation boundaries →
        </Link>
      </section>
    </>
  );
}
