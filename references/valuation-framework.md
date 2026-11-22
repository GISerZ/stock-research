# A-share Valuation Framework

Read [the research workpaper contract](research-workpaper.md) before preparing a deep-dive or valuation workpaper. It is the single definition of the common fields, input status, units, paths and versions; retain method-specific drivers and historical attachments. The manual workpaper is auxiliary evidence and does not replace original-source verification or the core packet.

## Method Selection

Choose valuation methods by company type:

- Stable consumer, healthcare, utilities, and mature leaders: PE, dividend yield, ROE stability, historical valuation band, and peer comparison.
- Banks, insurers, brokers, property, and asset-heavy companies: PB, ROE, asset quality, capital adequacy, leverage, and impairment risk.
- High-growth technology, software, semiconductor, and platform companies: PS, PE on normalized earnings, R&D efficiency, gross margin trend, and peer growth-adjusted multiples.
- Cyclical companies in materials, chemicals, energy, shipping, and equipment: cycle-adjusted PE, PB, commodity spread, capacity cycle, inventory cycle, and normalized margin.
- Conglomerates or companies with distinct segments: sum-of-the-parts.
- Cash-flow visible infrastructure, utilities, and concession assets: DCF or dividend discount as a cross-check.

## Required Comparisons

When data is available, compare:

- Current valuation against 3-year and 5-year historical range.
- Current valuation against direct A-share peers.
- Current valuation against Hong Kong, US, Korean, or global peers when the business model is comparable.
- Growth, margin, ROE, and cash-flow quality against valuation.

## Operating Assumptions Before A Rating

Start from verified financials and the business drivers that matter to the thesis, such as volume, price/product mix, unit costs or margins. Explain the low/base/high assumptions and their connection to sustainable parent-attributable profit or the chosen valuation driver, then bridge ownership, actual shares and supported financing/dilution scenarios to per-share value. Use the smallest model that explains the conclusion; a company need not disclose every generic operating metric. For cyclicals, explain peak versus normalized profitability rather than mechanically annualizing a strong quarter.

Researcher forecasts are assumptions grounded in verified history and explained operating evidence, not future facts awaiting verification. Missing broker coverage, the next periodic report not yet being published, or an unproven new business does not alone prevent modeling the existing business; an unproven contribution may be excluded. If the model is unfinished or a decisive assumption cannot be credibly bounded after an attempt, use the specific unrated reason in `position-building-and-risk.md` and name the remaining work instead of inventing scenarios.

## Horizon And Terminal Value

Use the separate driver/range/counterevidence/next-node chains in [research-workpaper.md](research-workpaper.md#假设计算及业务差异): revenue through volume/price/mix/consolidation; sustainable parent margin through costs/depreciation/expenses/tax/attribution; multiples through comparable business quality, returns, growth and capital needs. A shared paragraph or quarterly annualization is not an independent rationale for each.

When capital returns matter, attribute ROE with consistent flows and defensible average assets/equity; separate operating improvement from leverage. PB needs sustainable-return and capital-constraint evidence, not just a historical median. A steady-state `(ROE − g) / (equity cost − g)` cross-check requires consistent retention/growth, clean-surplus and sustainable assumptions with equity cost above growth; it is not a universal PB target. Banks/insurers have operating financing liabilities: do not mechanically apply industrial net debt, EV/EBITDA or simplified FCFF. Use an appropriate method and disclose asset-quality/regulatory-capital limits.

For a decisive dispute, reverse price into required earnings/margin or capital return and show the joint operating/multiple combination that changes judgment. For suitable positive PE, required parent profit = price × matching shares / PE; connect it to revenue and parent margin. Reuse existing result IDs, state held-constant terms and counterevidence. Conditional requirements are not observed consensus; sensitivity results are not another set of action bands.

Use the exact start/end and default 12-calendar-month convention in [research-workpaper.md](research-workpaper.md#研究期限与期末情景). The main question is value and price upside/downside at that endpoint, with interim business milestones used to reassess the thesis. The fiscal year is an earnings basis, not a second holding window.

For low/base/high scenarios, explain the earnings or other value driver the market could price at the endpoint, the applicable multiple or valuation basis, and the business evidence needed for that pricing. For PE, terminal price is the adopted terminal per-share earnings basis multiplied by the terminal PE; label whether that basis is current-year, next-year, NTM or normalized, and justify it. Do not mechanically select the endpoint's calendar year or roll every model to the following fiscal year. Forecasts remain assumptions; later annual disclosures may validate them after the price horizon ends.

Keep fiscal-year model value, supported terminal price, and current buy/hold boundaries distinct. If the same value is adopted as the terminal price, state why and reuse its result ID. Calculate terminal price change as `terminal price / reference quote − 1`; it is a conditional scenario, not a guaranteed price, probability-weighted expected return or measured chance of profit. Where supported, show dividend contribution separately for total-return scenarios and reconcile ex-dividend effects once. If the terminal bridge is unfinished or a decisive assumption cannot be bounded after an attempt, retain model values as such, leave unsupported terminal prices empty and apply the existing specific unrated reason; changing the horizon label does not complete that analysis.

Identify a small set of decisive operating milestones during the horizon, the disclosures available by each checkpoint, and evidence that would support or invalidate the thesis. Reassess on material disclosures/events and at the endpoint; include a six-month midpoint for the default one-year horizon, and choose checkpoints within the actual window for other horizons. No monthly price path is required. Separate operating realization from publication availability, and do not defer the original price-horizon review until a later full-year filing.

## Valuation Output

State:

- Current valuation level.
- Whether valuation is cheap, fair, expensive, or not meaningful.
- What assumptions must hold for valuation to be justified.
- What would cause valuation compression.
- Whether the current price offers a margin of safety for the intended holding period.

When evidence supports a rating, convert valuation scenarios into reproducible CNY/share bands for the stated holding period:

1. Identify the quoted **unadjusted** price, provider trading timestamp, and share basis. Verify material EPS, book value, cash flow, or share count inputs against the original filing. State whether the input is trailing, annual, forecast, or normalized; treat forecast figures as model assumptions.
2. Choose a method suited to the business. For PE, `scenario value = EPS × scenario PE`; for PB, `scenario value = book value per share × scenario PB`. For DCF or segment valuation, show the cash-flow/share-count or segment/share-count arithmetic. Explain why the low, base, and high multiples or discount rates are plausible using history, peers, business quality, and risk.
3. Show low/base/high scenario values and a margin of safety. A positive rating needs a numeric buy range and numeric hold range, plus a reduce/reassess level or event. Explain each boundary's calculation and relationship to the scenarios; do not present rounded bands as mathematical precision beyond the inputs.
4. State what would invalidate the bands: a new financial filing, changed share count, corporate action, earnings miss, governance event, industry shift, or passage of the stated horizon. Recalculate after such an event.

For `减持 / 回避`, write `暂不买入`; show a numeric reduce level only if the evidence supports it, otherwise a concrete reassessment event. If a latest material filing or timestamped quote is missing, output `数据不足，暂不评级` and no fabricated numerical band. A scenario range is a model output, not a promise of future prices.

## Verified Inputs And Calculation Basis

Before calculating scenarios, adopt inputs in the [workpaper](research-workpaper.md). The report's compact table displays those same records and assumptions rather than maintaining a second input set:

| Workpaper ID | Input | Value and unit | Financial period / valuation date | Basis and verification status | Original source and page / assumption rationale |
|---|---|---|---|---|---|

Include only inputs that affect the conclusion. Distinguish verified disclosure, verified broker forecast, unverified lead, and researcher assumption. A researcher forecast may be used when its historical base and share basis are verified and its operating assumptions are explained; missing broker coverage does not require inventing consensus or withholding all analysis.

- Verify current issued shares against a dated original disclosure and subsequent capital changes. Never infer current shares from reported profit divided by rounded basic EPS: basic EPS uses weighted average shares. Show potential dilution separately, with the event, assumed shares, and treatment of proceeds and earnings; do not treat an issuance ceiling as completed issuance.
- Broker-index EPS remains a lead even when recent. Before using it or calculating a median, verify the original report, actual publication date, explicit fiscal year, share basis and intervening events. For an aggregate, list the retained institutions/dates, sample size and exclusions; avoid counting several reports from one institution as independent consensus. Do not map a relative `this/next year` field to a fiscal year without verification. Saying “not company guidance” does not satisfy these checks.
- Use consolidated parent-attributable profit/equity consistently. Subsidiary profit is not automatically attributable to the listed company; account for minority interests and consolidation changes. Use restated comparative figures where applicable.
- Single-quarter flow = current cumulative flow minus the preceding cumulative flow in the same year. TTM flow = previous full year + current year-to-date − comparable previous year-to-date, on a consistent basis. Do not annualize a seasonal half-year without explaining the seasonal assumptions. Balance-sheet amounts are point-in-time stocks, not cumulative flows.
- Distinguish monetary funds, cash equivalents, unrestricted available cash, and net cash. For net cash/debt, show the included debt categories and cash deductions on matching dates/scopes. Distinguish capital expenditure from net investing cash flow; label operating cash minus asset purchases as a simplified measure rather than complete FCFF.
- Equity adjustments for dividends, buybacks or transactions must use only the incremental effect after the balance-sheet date and explain treasury-share/accounting treatment. Do not deduct amounts already reflected in equity or add financing proceeds directly to equity without the corresponding obligations.
- Negative earnings do not support a positive earnings multiple; negative or severely depleted equity can make PB misleading. Use an appropriate alternative, a clearly labelled reverse earnings requirement, or an unrated limitations analysis rather than force a valuation.

## Reusable Calculations And Price Boundaries

Calculate each material derived number once in the workpaper's `derived`, retain precision through intermediate steps, and reference the result IDs in scenarios, sensitivity and the adopted `final_decision`. Reuse them across the conclusion, financial discussion, debate and action plan. State rounding for final display; a changed denominator requires a changed label. Before delivery, manually reconcile key arithmetic, units and repeated values. This is part of research, not permission to run workspace-prohibited validation commands.

Use these definitions consistently for positive prices and model values:

- Margin of safety = `1 − current price / model value`.
- Upside/downside to model value = `model value / current price − 1`.
- Premium/discount to model value = `current price / model value − 1`.

For example, price 80 and model value 100 imply 20% margin of safety and 25% upside; they are not interchangeable percentages. Omit ratios whose denominators are nonpositive or not meaningful.

Derive every buy/hold/reassess boundary from the scenarios and an explained discount or multiple; mark equality at shared boundaries so actions do not overlap. Explain why the selected discount compensates for the identified uncertainty instead of adding an unexplained round-number range. Check whether the same risk is already reflected in earnings, the multiple or discount rate before adding a further haircut. A low scenario is not a loss floor, and an unweighted scenario table cannot establish expected return or event probabilities.

Relate model return potential to a stated return requirement or comparison appropriate to the horizon and risks; label researcher judgment rather than inventing a user target or a universal threshold. A future-year valuation is not automatically a realizable sale price during the holding period. When discussing horizon total-return scenarios, explain the price-realization assumption and any supported dividend contribution separately, avoiding double counting distributions and ex-dividend effects. Keep these scenarios distinct from probability-weighted expected returns.

For a material, supported assumption dispute, vary the decisive driver within an explained range and state whether the current-price case survives, requires a different price, or cannot be bounded. Ordinary disagreement need not disappear before a rating. Reflect the remaining uncertainty in confidence and price compensation, while retaining genuine fact/solvency constraints under `position-building-and-risk.md`.

State the valuation fiscal year, valuation date, intended holding horizon and next mandatory update. Explain why that earnings basis represents the horizon; if only an earlier year's data is defensible, disclose the gap and its effect on conviction rather than silently rolling it forward. The core conclusion expresses the workpaper's adopted `final_decision`; other sections use the same result. Sensitivity values and agent proposals become current boundaries only after explicit adoption, boundary/rating review and a new exact version. For changed inputs, quote-only updates or chip-only supplements, follow the workpaper's update table; a new quote changes price-dependent metrics and may change the rating/status without moving the model bands. Follow `position-building-and-risk.md` before any new-money action outside those bands.
