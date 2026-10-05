# Video script (3–4 minutes)

Team DIU Comebackhobena · Jachai · Track 05 with a Trust & Risk engine.
Screens: live dashboard <https://jachai-eta.vercel.app>. All data is synthetic;
say so once at the start and once in the results. Numbers below are taken from
`reports/summary.md`, `reports/final_test.md` and the fast-profile simulator
report; re-check them if any report is regenerated.

| Time | Screen | Voice-over |
| --- | --- | --- |
| 0:00–0:25 | Home page | "A customer pays a shop **Tk 10,000** by Bangla QR. Nothing is bought. The customer walks out with about **Tk 9,815** in cash. The shop has just become an unlicensed cash-out point, the Tk 30,000 daily cash-out limit is bypassed, and there is no trail." |
| 0:25–0:55 | Home page | "Why upay cares: it loses agent cash-out fees and pays interchange on off-us QR, and from 1 October, with zero QR fees and an incentive under Tk 2,000, splitting gets attractive. Acquirers are expected to monitor merchants with unusual patterns and stop cash-outs. The blunt answer is a limit on every shop. That hurts honest wholesalers and festival sellers. Jachai asks one question per shop: **real commerce, or a hidden cash-out?** Everything you see runs on synthetic data." |
| 0:55–1:35 | Alert queue → case view | "This is the analyst's queue: shops that **need review**, never 'fraud'. Open one. Three scores: payment, shop and network. The top three reasons, in English and Bangla, every number filled in by code from the shop's own data: received about Tk 75,000 a day where a shop like this expects about Tk 14,000. The timeline shows when it started." |
| 1:35–2:05 | Case view: linked shops + decision | "Here is the network view. These shops share payers who went past the daily limit across three or more shops on the same day: a limit-bypass ring no single shop would reveal. The analyst decides: clear, monitor, educate, offer an agent contract, restrict or escalate, always with a reason, in an append-only log. Nothing is blocked automatically." |
| 2:05–2:45 | Policy simulator | "Same month, five policies. A blanket Tk 1 lakh limit stopped about a quarter of the misuse taka and restricted 12 honest shops in this replay. Rules and Jachai each stopped about 73% with no honest shop restricted. Move a slider, say analyst capacity, and every policy is replayed with identical payments. Policy E turns confirmed high-demand cash-out points into licensed agents. This replay is a small diagnostic, not a forecast." |
| 2:45–3:30 | Trust page | "Honest results. On three validation seeds rules alone ranked shops better, PR-AUC 0.90 against our 0.77, and on the single final test rules were stronger too, 0.84 against 0.58. Why? Our synthetic world and our rules came from the same typologies, so rules look unrealistically good. When misusers adapt and stop using round amounts, Jachai held up better than rules, and it found limit-bypass rings that rules nearly missed: 0.59 against 0.02 recall. We report all of it." |
| 3:30–3:50 | Home page | "Jachai: protect honest shops, review the right ones, and turn the leak into new upay agents. Built by Team DIU Comebackhobena. Thank you." |

Recording tips: show the browser at laptop width; rehearse once with the API
asleep to confirm demo mode; keep each screen on for at least five seconds.
