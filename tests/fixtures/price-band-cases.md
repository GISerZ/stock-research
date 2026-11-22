# Rating and price-band evaluation cases

Run these cases against any rated short answer and the deep-report template. A number in this file is synthetic; it must never be quoted as a live stock price or valuation.

## A. Positive rating with reproducible bands

Fixture: An A-share has a verified original filing with attributable EPS of CNY 5.00 per share for the chosen trailing period. A current unadjusted quote is CNY 58.00 at a stated Beijing trading timestamp. Historical and peer evidence supports 12x, 16x, and 20x PE scenarios for a 12-month holding period. The base scenario is CNY 80.00/share. A 25%-35% safety margin to that base value gives CNY 52.00-60.00/share.

Expected: If the thesis supports `买入`, `增持`, or `持有`, state the rating and horizon, timestamped unadjusted price, verified EPS and source, scenario PE evidence and values (60/80/100), arithmetic for the buy band (80 × 65%-75% = 52-60), a numeric hold band (for this example 60-100), a reduce/reassess level or event (above 100 or material thesis break), and assumptions that would invalidate the bands. Do not claim the PE scenarios were reported facts.

## B. Negative rating with governance risk

Fixture: A current official governance disclosure establishes a material unresolved risk. The current quote and its timestamp are available, but no reliable valuation anchor supports an entry price.

Expected: A justified `减持` or `回避` states `暂不买入`, explains the cited official risk, and gives only an evidence-based reduction threshold or a clear reassessment event such as withdrawal of the regulatory action and a newly verified filing. No invented buy or hold band. If a numeric reduction level is given, show its calculation. State the horizon and quote timestamp even for a negative rating.

## C. Missing key evidence

Fixture: The latest report cannot be confirmed, or the only quote lacks a reliable trading timestamp.

Expected: `数据不足，暂不评级`; list the missing facts and the next verification step. No buy, hold, reduce, or target price is manufactured. Save a limitations report if this is a deep dive.

## Baseline review before edits

- Existing `SKILL.md` required a five-tier rating only when evidence supports it, but did not require a buy/hold band or valuation arithmetic for any rating.
- Existing `references/report-template.md` had only a free-form “初始建仓区间”; it did not force a hold band, horizon, quote timestamp, source verification, or a negative-rating `暂不买入` branch.
- Existing `references/position-building-and-risk.md` allowed `回避` for insufficient evidence, conflicting with `SKILL.md`'s no-rating rule.

Therefore A/B/C could not be satisfied consistently before the revision.
