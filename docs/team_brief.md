# Team explanation card

Every member should be able to say this in about 30 seconds:

> “Jachai helps an analyst decide which Bangla QR merchants need review. It
> combines three signals: payment behaviour, whether a shop’s turnover looks
> plausible compared with similar shops, and payer–shop network links that can
> reveal coordinated rings. It gives reasons in English and Bangla, but it never
> decides guilt or blocks anyone. A human records every decision. Our results
> are synthetic: rules are stronger in the normal simulated world, while Jachai
> is more robust in our configured non-round evasion check.”

## Three signals in one sentence each

| Signal | Plain explanation |
| --- | --- |
| Payment | “Does this payment look unusual for this payer and shop at this moment?” |
| Shop | “Is this shop receiving turnover that looks implausible for similar shops?” |
| Network | “Are the same payers connecting several shops in a way that suggests a ring?” |

## Non-negotiable answers

- **Does AI decide?** No. Scores prioritize review; an analyst decides.
- **Is it real customer data?** No. The world, labels and cases are synthetic.
- **Why not rules only?** Rules are strong on known patterns; Jachai adds shop
  and network context and we disclose where it helps and where it does not.
- **Is this deployed production ML?** No. The public dashboard is a stable,
  cached synthetic demonstration; a real deployment needs representative data,
  governance and durable operations.
