# Position Building And Risk Rules

## Rating Scale

When verified facts and an explainable model support a judgment, use exactly one primary rating:

- 买入: The current price offers clearly attractive model-based return potential relative to the stated return requirement or comparison; the downside and thesis-failure cases have been assessed, with no unmet material hard constraint and a valid current new-money path.
- 增持: There is a positive current new-money case, but its return cushion or thesis confidence is weaker than for 买入; staged participation has a stated rationale. Existing ownership is not required, and staging alone does not determine this rating.
- 持有: A valuation judgment is possible, but new money lacks sufficient attraction at the current price or must await a justified material entry condition. Existing ownership alone does not establish a reason to hold.
- 减持: The thesis has weakened, or current return potential no longer compensates for the assessed risk.
- 回避: Supported material operating, governance, solvency or valuation risks defeat the participation case. Technical weakness alone is insufficient.

Explain the return requirement or comparison used, its basis, and how the exact horizon, supported terminal scenarios, downside and confidence distinguish the chosen rating from the adjacent tier. Follow the default forward 12-month convention and terminal-value bridge in `research-workpaper.md` and `valuation-framework.md`; do not treat fiscal-year model upside alone as a one-year return case. Without a user return target, label the comparison as researcher judgment. Use no universal upside cutoff, fixed discount, score or desired rating distribution. Market trend and catalysts inform the thesis and timing; all need not simultaneously be favorable for every strategy.

State three separate judgments: rating, research confidence (`高 / 中 / 低` with the decisive reason, not a measured probability), and new-money status (`仅观察 / 条件满足后复核 / 条件已满足`). Lower confidence affects conviction and the required price compensation; it does not automatically mean no rating.

If no rating is supportable, retain `数据不足，暂不评级`, omit executable price bands, and identify the reason:

- `事实缺口`: Latest material filing, actual issued shares, timestamped quote or another decisive historical fact cannot be verified; name the missing original and its impact.
- `模型未完成（研究未完成）`: Facts are verified, but the researcher has not completed a defensible operating/valuation model; name the unfinished analysis rather than automatically waiting for future disclosure.
- `模型无法可靠界定`: Modeling was attempted, but a decisive input cannot be bounded with evidence; state the input, attempted basis and consequence.

Bounded forecast disagreement belongs in scenarios and sensitivity, not automatically in these categories. Do not substitute 持有 or 回避 for unfinished research or a fact gap. A rated short answer follows the same price-band rules as a full report.

## Price Ranges By Rating

Use this mapping for the report and the [workpaper's `final_decision`](research-workpaper.md); numeric ranges are CNY/share:

| Rating | Buy / hold ranges and entry ceiling | Current new money and reassessment |
|---|---|---|
| `买入 / 增持` | Numeric buy and hold ranges with adopted result references, equality and a price ceiling | Quote inside the effective buy range, research-level necessary conditions met, `条件已满足`; give an evidence-based reduce/reassess level or event |
| `持有` | Numeric buy and hold ranges with the same boundary requirements | Buy band may lie below the quote or await a justified material entry condition; explain current status and what would permit new money, without implying ownership |
| `减持 / 回避` | `buy_range / hold_range / price_ceiling_ref=null`; report says `暂不买入` | No current trial/add instruction; only a supported reduce/reassess level or a concrete event, with no fabricated entry price |
| `数据不足，暂不评级` | The same three fields are null; no numeric executable buy/hold/reduce bands | `仅观察`, the specific unrated reason and work needed for reassessment; model scenarios remain illustrative |

For any supported rating, show quote time, horizon, verified financial base, valuation scenarios, formulas, safety margin and invalidation triggers. Do not derive bands from chart support alone when valuation is missing. A `持有` decision does not authorize current new money unless its effective buy band and necessary conditions are satisfied. `仅观察 / 条件满足后复核` never accompanies a current trial/add instruction; a lower conditional band is a future reassessment condition. Review a rating if its current-price case changes.

## Position-Building Plan

Do not recommend all-in entry.

Use staged language:

- 观察: Track without buying.
- 试仓: Discuss staged entry only when the current buy band and its evidence/risk gates are satisfied; no default percentage.
- 确认仓: Reassess on thesis-specific confirmation, such as earnings, cash conversion or verified delivery; confirmation does not waive valuation or require all generic indicators to improve.
- 加仓: Add only when the original thesis improves or the risk-reward becomes more attractive.
- 减仓: Reduce when valuation stretches, trend breaks, catalyst fails, or risk rises.

State the intended period with exact start/end dates and whether it is user-specified or a research assumption. A one-year research horizon does not require holding for a year or prevent earlier reduction/reassessment when price, evidence or risk changes. Keep interim checkpoints separate from terminal price scenarios; quote-only and auxiliary updates retain the original endpoint.

Without user-provided holdings, intended allocation, horizon and risk/loss limits, give conditions rather than numeric position sizes or maximums. Calling a percentage “of planned stock allocation” does not supply the missing risk budget. If the user requests sizing and supplies the necessary constraints, show the denominator and how the allocation respects those constraints; do not substitute a preset 20%–30% or 60% rule.

## One Final Plan

The workpaper's `final_decision` records the adopted conditions; the core conclusion is their authoritative reader-facing expression. Link the exact workpaper version and decision ID, using the same `basis` horizon/fiscal year, quote, rating, confidence, new-money status, result IDs, boundaries/equality, gates and invalidation. The later plan explains that decision without creating different entry prices, percentages or looser gates. Record a replaced plan in `basis.supersedes` with its exact file, location, scope and reason. Reconcile any mismatch before delivery; a stale workpaper and a revised report are not two valid decisions.

Agent proposals and sensitivity values remain proposals/model outputs until the lead explicitly adopts them after boundary and rating review; reject or replace conflicting proposals. Adjacent action ranges assign a shared endpoint to one side only, and the entry ceiling cannot exceed the effective buy upper bound. Keep the adopted boundary and comparison operator through display rounding; a cheaper price or a sensitivity result does not waive a hard constraint.

New evidence can justify a higher entry range, but a “confirmation”, “evidence-first” or “opportunity-cost” branch must first update EPS/BPS, multiples, share basis and margin of safety as applicable, publish the revised numeric band and supersede the old one. Until that is done, the branch triggers research only, not a trial/add position at an unspecified price. A fallback entry branch always needs a valuation-based price ceiling.

Separate an estimate's candidate band from its current activation status (`仅观察 / 条件满足后复核 / 条件已满足`). If a material supported hard constraint remains unmet, give an observation-only new-money plan. It is permissible to show conditional model bands, but do not pair “only observe” with a current trial/add instruction.

For each hard gate, state the supporting evidence, material effect on valuation, solvency or the thesis, and observable release metric/event with period and source. Distinguish a fact gap, confirmed material risk, assumption dispute and helpful confirmation. If a necessary public fact cannot be verified, name it and retain observation status. Future-report nonpublication, ordinary volatility or an unsteady chart is not an automatic veto; when formal confirmation is necessary, explain why existing evidence cannot bound the material risk.

For a supported material assumption dispute, assess the effect through `valuation-framework.md` before retaining a hard gate. Compare the benefit of waiting with the uncertainty accepted now, without treating opportunity cost as permission to waive price ceilings. Risks that can be bounded may affect the model or required price compensation; some governance or solvency risks remain unacceptable at a cheaper price. Newly verified business evidence can support upward reassessment without every indicator improving together.

## Risk Triggers

Include concrete triggers:

- Financial report misses expectation.
- Gross margin, net margin, ROE, or cash flow deteriorates.
- Receivables, inventory, debt, pledge, litigation, or impairment risk rises.
- Industry policy turns negative.
- Main product price, order, shipment, or capacity utilization weakens.
- Stock breaks a key support zone with rising volume.
- Sector rotation weakens the stock's relative strength.
- Official disclosure contradicts the investment thesis.

If any trigger is central to the thesis, state that the rating should be reviewed when it occurs.
