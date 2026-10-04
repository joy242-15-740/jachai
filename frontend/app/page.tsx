import Link from "next/link";
import { PageTitle, Panel } from "@/components/ui";

const CARDS = [
  { href: "/queue", title: "Alert queue", text: "Shops that need review, highest risk first, with the main reason." },
  { href: "/simulator", title: "Policy simulator", text: "Replay one month under five policies and compare outcomes." },
  { href: "/notice", title: "Merchant notice", text: "A polite Bangla notice preview with an appeal form." },
  { href: "/trust", title: "Trust", text: "Results vs baselines, robustness, fairness, data card and limits." },
];

export default function Home() {
  return (
    <>
      <PageTitle
        title="Real commerce, or a hidden cash-out?"
        subtitle="Jachai scores Bangla QR payments and shops, explains why, and leaves every decision to an analyst. Don't limit every shop: find the few running hidden cash-outs, protect honest shopkeepers, and turn the leak into new agents."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        {CARDS.map((c) => (
          <Link key={c.href} href={c.href}>
            <Panel>
              <h2 className="font-semibold">{c.title}</h2>
              <p className="mt-1 text-sm text-muted">{c.text}</p>
            </Panel>
          </Link>
        ))}
      </div>
    </>
  );
}
