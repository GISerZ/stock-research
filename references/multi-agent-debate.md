# Independent Agent Debate for A-Share Deep Dives

Use this workflow for a single-stock deep dive or when the user explicitly requests independent-agent debate. It requires runtime collaboration tools that actually create separate agents. The lead researcher remains responsible for source verification, valuation, rating, and the saved report.

## Shared Brief and Roles

Before dispatch, the lead researcher collects and checks the evidence, then sends every agent the same read-only brief:

| Field | Required content |
|---|---|
| `research_id`, `brief_ref` | Stable ID for this research run and the exact frozen brief path/version; retain that ID on recovery. A later research run names the inherited run separately. |
| `code`, `research_date`, `holding_horizon` | Identified stock and exact decision start/end dates plus horizon source, matching the adopted workpaper. Default to the next 12 calendar months for a new horizon; retain the original endpoint for quote-only or auxiliary updates and state the valuation fiscal year separately. |
| `evidence_path`, `collected_at`, `collection_completed_at` | Exact packet path, collection start and end times; legacy packets may lack the end time. |
| `research_as_of` | Explicit information cutoff for all materials in the frozen brief; not inferred from the collector's start time. |
| `verified_facts` | Decisive facts with original source URLs, reporting periods, units, and calculation bases. |
| `workpaper_ref` | Exact saved workpaper path/version, contract version, input/assumption/result IDs and model status, including fiscal-year model values, proposed terminal-price scenarios/quote-relative changes, their realization assumptions and decisive interim milestones. Missing terminal support remains an explicit gap; pending proposals remain separate from the adopted `final_decision`. |
| `quote_time_and_phase` | Unadjusted price, provider trading time, and auction/continuous/post-close phase. |
| `source_status_and_gaps` | Failed, stale, missing, or conflicting sources and material unresolved questions. |
| `chip_snapshot_if_available` | Exact chip snapshot path/version, collection time, actual data day, mode, algorithm and limits; include explicit failed/unsupported coverage instead of inventing a peak. |
| `sentiment_and_narrative_review` | Exact sentiment/market snapshot versions and narrative-review attachment, their cutoffs and coverage gaps, short-term horizon, event IDs, sourced prior expectations, competing behavioral hypotheses, price/sector feedback and invalidation conditions; preserve snapshot statuses separately from later manual review. |
| `user_constraints_if_known` | Holdings, risk tolerance, and position limits only if the user supplied them. |

Keep the brief compact: reference exact saved files, decisive fact/input/result IDs and original-source pages, rather than copying whole PDFs or unrelated historical reports. The packet is a common input, not proof that every observation is verified. Structured financial observations and PDF excerpts retain their existing verification status. Include the lead's working operating/valuation assumptions, their evidence basis and ranges separately from verified facts, so agents can challenge a model rather than demand that future outcomes be proven. Each agent reads the same snapshot and may identify further sources, but the lead researcher must check any new material fact against its original source before using it in a conclusion. Agents do not edit the packet or the final report.

All investment and risk roles assess the same endpoint and the terminal-value bridge in `valuation-framework.md`: what earnings/multiple could be priced then, which interim evidence supports it, and what invalidates it. A fiscal-year model value alone is not a one-year return case, and later annual verification does not extend the price horizon. A changed horizon is a model/proposal change under `follow-up-workflow.md`; record its old/new dates and obtain affected views on the revised plan without adding roles or rounds.

All roles use the same frozen chip version under `chip-analysis-framework.md`. Chip costs are modeled market structure, not verified main-player accounts or fair value; source/model quality does not map to rating, confidence or a hard gate. Preserve the existing fact/assumption/risk/watch-item classification and sensitivity rules. A material chip correction or supplement uses the same common-update process below; an affected role that cannot review it remains incomplete. Do not add roles or rounds just to obtain agreement about a chip interpretation.

The brief's `research_as_of` is the common information cutoff. Each quote, filing and reviewed input retains its own observation/publication/retrieval time. If the lead researcher verifies a material new fact after dispatch, record its source and time in a common supplement and send the same supplement to both investment agents. If risk review has begun, send it to all three risk agents too. Obtain updated views on affected claims and constraints before calling the run complete. If an affected role cannot review the update, mark the run `部分完成` and do not rely on its earlier conclusion as if it covered the new fact.

Dispatch independent bull and bear agents with isolated context when supported (`fork_turns: "none"`), each with the brief, role, task, and output contract. They may run in parallel. Keep the rebuttal round and the later risk review in separate stages; if there are fewer concurrency slots, run independent agents sequentially. Do not treat role-playing by one agent as a completed independent-agent run.

Set a bounded deadline per role/stage and a total effort budget before dispatch, respecting the runtime and user limits. Do not replace failed roles repeatedly or add rounds to obtain agreement; disclose the missing work at the deadline and proceed only with supported conclusions. User-required independent review remains incomplete when a required role cannot return.

## Run Record And Recovery

At publication, use the existing adopted-final-workpaper/final_decision/report entry below for one closeout: reconcile the selected quote/provider time, inherited horizon/cutoff, exact inequalities/equality, adopted workpaper/result IDs, report and every actual cited attachment version (including registration). Enter only observed generation/registration times at their real precision; no predicted future timestamp. The current-adoption entry states the single current version directly; put superseded versions and the reasons in separate history, rather than appending contradictory “final” labels. This does not add a status file or certify runtime acceptance. A material error found after freezing still gets a preserved new version and explicit replacement scope.

For a new deep dive or explicit independent-agent run, the lead maintains `research/evidence/manual/YYYY-MM-DD-CODE/run-record.md`, including when independent agents are unavailable. Use the template below as a compact index of actual actions and results, not a scheduler or a replacement for returned role content. Saving, freezing and report-relative links follow [collection-and-storage.md](collection-and-storage.md). The report links the exact record version; do not select a newer file merely because it exists.

Stage status is `未执行 / 进行中 / 已返回 / 缺失`. `进行中` means work actually started; a dispatch alone is never `已返回`. A deadline, failure, omitted claim or inaccessible return is `缺失`, with the reason and known dispatch retained. `已返回` records an available result, not agreement or sufficient evidence. For mixed results, identify the returned and missing roles/claims separately. Keep inherited history separate from this run's stages. The six stages index the existing workflow; the frozen plan is the proposal for risk review, not the adopted final decision.

```markdown
# 独立审查阶段记录

- 研究ID／股票／日期：
- 记录精确版本／记录时间／承接的记录或报告精确版本：
- 本次范围（新研究／恢复／报价续作／局部筹码补件）；继承内容、原截止与未覆盖的新材料：
- 共同截止 research_as_of（带时区）；各报价／披露／补件仍保留自身时点：
- 研究期限的明确起止及来源／估值财年；继承或重置范围／期末情景与期间关键节点的精确底稿定位：
- 冻结简报、核心／情绪／筹码／叙事附件精确路径及版本：
- 底稿精确版本／契约版本／输入、假设、结果ID及模型状态（无新底稿时引用现有计算稿）：
- 冻结待审方案精确版本／提议结果ID（尚未形成时写未形成）：
- 已采纳最终底稿／final_decision ID／报告精确版本（尚未裁决时写未采纳）：
- 原定角色／阶段时限与总预算、已用时间／调用量及剩余（仅记录可取得的实际值，未知写未知）：
- 本次独立流程：完成／部分完成／未执行；历史流程及其适用范围另列：
- 事实核验缺口／模型状态／辅助覆盖缺口／文件验收状态（分别记录）：

| 阶段 | 本次状态 | 实际结果位置及所用输入／方案精确版本 | 缺项或继承范围 |
|---|---|---|---|
| 证据准备 | 未执行 | | |
| 多空首答 | 未执行 | | |
| 逐条回应 | 未执行 | | |
| 方案冻结 | 未执行 | | |
| 三方风控 | 未执行 | | |
| 主研究裁决 | 未执行 | | |

| 角色 | 实际运行时标识（未创建写未创建；失败标识另留） | 实际接收的简报／补充／待审方案版本 | 首答状态／结果位置 | 逐条回应状态／结果位置 | 风控状态／结果位置 |
|---|---|---|---|---|---|---|
| 多头 | | | 未执行 | 未执行 | 不适用 |
| 空头 | | | 未执行 | 未执行 | 不适用 |
| 激进风控 | | | 不适用 | 不适用 | 未执行 |
| 保守风控 | | | 不适用 | 不适用 | 未执行 |
| 中性风控 | | | 不适用 | 不适用 | 未执行 |

| 保留主张ID／原答位置 | 应回应角色／实际标识 | 发出位置／时间 | 回应状态／返回位置 | response_status | 分歧类型、证据与主研究者处置 |
|---|---|---|---|---|---|
| B1—B3／S1—S3逐项按实际保留，不凑满 | | | 未执行 | 未取得 | |

| 共同补充ID／精确版本 | 原始来源与可获得／检索时间 | 主研究者核验说明／补充截止 | 受影响主张、结果、方案或约束 | 应接收角色及原因 |
|---|---|---|---|---|
| | | | | |

| 补充ID／角色／实际标识（每个应接收角色一行） | 实际送达时间／工具结果位置（未送达或不可确认则明写） | 更新意见状态／返回位置 | 已覆盖版本、变化或有理由的无变化；缺项 |
|---|---|---|---|
| | | 未取得 | |

- 缺失／过期阶段与原因；已返回但仍有效的部分：
- 下一动作：补哪项、交给谁、用哪个精确版本、截止／剩余预算；无剩余工作则写无：
```

Result locations must remain readable after interruption: save the decision-relevant returned content and its evidence references in a versioned attachment, or point to an already saved result/plan section. Label a preserved summary as a summary; do not invent a raw transcript, runtime ID, delivery time or return that was not retained. An uncreated role and a failed dispatched role remain distinguishable; an unsupported return is recorded as received but cannot support a conclusion or workflow completion.

Use only actual rows; write `无` when there are no retained claims or common supplements, and `未取得` for unknown returns or delivery details. Do not leave template rows as if they were performed work.

Keep one row per retained opposing claim, using the existing `B1`–`B3` / `S1`–`S3` IDs. Record excluded duplicates and why; if no material claim was retained, preserve the agent's explicit output. Fill `response_status` with `answered / unresolved / evidence_missing` only from an actual response. A missing reply is `缺失 / 未取得`, never an invented `evidence_missing`. A sourced disagreement can be answered while remaining a forecast dispute.

For each common supplement, record source times, verification, affected IDs/constraints and required recipients. Send the same verified material update to both investment agents and, once risk review has started, all three risk roles; risk roles started later receive it with the frozen inputs. Track delivery and updated opinions per recipient. A successful send is not proof of reading or an updated view; an affected role must identify the covered version and update its view, or explain why it is unchanged. Otherwise record `未取得` and keep the affected review incomplete under the existing completion rule. Do not advance every source's timestamp when only a quote or one attachment changes.

On recovery:

1. Read the exact record linked by the interrupted report/brief, then any explicitly named continuation record. If none exists, start a new record from readable saved outputs; label unretained IDs, delivery and returns as unknown/missing, without backfilling historical workflow completion.
2. Read the named brief, workpaper, proposal and supplements. Determine which returned stages remain valid at their original cutoff and which inputs or action conditions changed; record the inherited scope and invalidate only affected review coverage. A missing risk return does not erase readable investment responses.
3. Retrieve outstanding results from the original roles when possible, then send only missing claims or affected updates within the existing deadlines and total budget. Do not repeat readable valid stages, reset the budget on recovery, repeatedly recreate failed roles or add debate rounds for agreement. At the limit, disclose missing work and preserve the supported conclusions.
4. Freeze a new record version after the actual continuation and align its gaps, next action and current-run status with the report. Keep the reviewed proposal separate from the lead's final adjudication and adopted workpaper version.

A quote continuation inherits unchanged operating assumptions/results at their original cutoff, while the lead recalculates quote-dependent metrics and reassesses rating/new-money conditions under [research-workpaper.md](research-workpaper.md). A chip-only supplement inherits the named fundamental report and model, and records the new chip/quote coverage separately. Neither inherits fresh agent approval. A local supplement that starts no new independent round reports this run `未执行` and the historical run's status/scope separately. If new material changes affect claims, valuation or actions, use the common-update process; absent affected updates cannot be described as reviewed. A started but incomplete continuation remains `部分完成`, even if its inherited debate was complete.

## Investment Debate

The bull tests the strongest evidence-backed upside thesis and its failure conditions. The bear tests the strongest downside thesis, valuation fragility, and missing evidence. Each returns at most three material claims using this record:

| Field | Meaning |
|---|---|
| `claim_id` | Unique within the report: `B1`–`B3` for bull, `S1`–`S3` for bear. |
| `role`, `statement` | Speaker and one concise, testable proposition. |
| `evidence_refs` | Direct source URL or packet location, with date/period and units for numbers. |
| `fact_or_inference` | Label sourced fact separately from the agent's interpretation. |
| `counterpoint` | Strongest foreseeable objection. |
| `invalidation` | Observable event or datum that would defeat the claim. |

When a retained claim depends on sentiment, address the same event IDs and cutoff from `sentiment-framework.md`: distinguish incremental facts from recirculated stories, challenge the prior-expectation baseline and psychological inference, and give an alternative explanation for price/sector feedback. Keep the short-term horizon distinct from valuation. Do not infer investor populations or account motives from sampled posts, or fill the three-claim limit with unsupported sentiment claims; no extra role or round is required.

The lead researcher deduplicates the first-round records and sends each side every retained opposing claim for **one** response round, preferably by following up with the same independent agent. For every claim sent, the agent returns the opponent `claim_id`, a sourced rebuttal or concession, and `response_status`: `answered`, `unresolved`, or `evidence_missing`. It must return `evidence_missing` rather than omit a claim it cannot address. Repeating a position without new evidence does not resolve a claim. No agent supplies the final stock rating, invented catalyst probability, or unsupported target price.

The lead researcher checks source dates, accounting basis, quote phase, and material figures; deduplicates claims; and records the claim, rebuttal, evidence, and disposition. Decide by evidential strength and relevance to the holding horizon, never by speaker count. Distinguish a fact error/gap from an assumption dispute, confirmed material risk or watch item. Keep material factual conflicts unresolved when the original or comparable basis is missing; agents need not agree on forecasts. The root's Portfolio View explains how the result relates to the user's known constraints and holding period.

## Risk Review

After the investment debate, the lead researcher drafts a conditional plan or an observation-only plan when evidence does not support a rating. Send that same plan, the brief, and the unresolved claims to three independent risk agents:

The pending plan names the exact workpaper version and the result IDs it proposes to adopt, with boundary equality, gates and new-money status. It is a proposal, not a second adopted `final_decision`; all risk roles review that same plan/version. After adjudication, save the adopted conditions in the workpaper's `final_decision` under [research-workpaper.md](research-workpaper.md), and point the report header/core conclusion to that exact final version and decision ID. Preserve the reviewed proposal's version and distinguish inherited review scope when results change; no unadopted agent band or sensitivity value enters the current action plan automatically.

- **Aggressive:** Check opportunity cost and whether the plan rejects supported upside for weak reasons; identify conditions for justified exposure.
- **Conservative:** Check financial, governance, valuation, liquidity, event, and downside risks; identify conditions that make exposure unsafe.
- **Neutral:** Check whether evidence, holding period, and any known user constraints match the proposed action and sizing.

Each returns `role`, `risk_facts` with sources, `plan_weakness`, `required_revision`, `hard_constraint_or_watch_item`, and `reassess_trigger`. Within these fields, classify the objection as a fact error/gap, assumption dispute, confirmed material risk or watch item. A proposed hard constraint needs evidence or an existing contract requirement, a material valuation/solvency/thesis impact, and an observable release condition; a watch item is monitored. Missing future reports or ordinary forecast disagreement alone is not a hard constraint. Without user-provided holdings or risk tolerance, position discussion stays conditional and does not invent a personal allocation.

The lead researcher adjudicates conflicting reviews from evidence rather than a vote. Assess the sensitivity of supported material assumption disputes using `valuation-framework.md` within the existing budget, then revise the draft at most once. Retain as hard constraints only substantiated blockers under `position-building-and-risk.md`; disclose remaining bounded disagreement with its model impact and confidence. If a surviving hard constraint remains unmet, withdraw the affected action, give an observation-only plan, and name the evidence, impact and release condition. If key modeling remains unfinished, record research incompleteness rather than adding agents or labeling it a company fact gap. The existing price-band contract always wins: if the latest material filing, share basis, or timestamped quote cannot be verified, state `数据不足，暂不评级`, give no numeric trading ranges, and do not set a position size. No debate or risk opinion can override that gate.

## Completion and Reporting

Record the actual mode (`完成`, `部分完成`, or `未执行`), participating roles, failed or absent roles, and unresolved claims in the exact run-record version linked by the report. `完成` requires bull and bear first-round outputs, one response for every retained opposing claim on both sides, all three risk reviews, and updated views on any later material fact. An explicit statement that no supported claim or objection was found counts as an output; a missing response does not. A failed, timed-out, or unsourced agent output is not evidence; mark a started run `部分完成`, disclose the missing round, and continue only with verified material. If collaboration tools are unavailable, say `独立 Agent 辩论未执行`. For a deep dive without an explicit independent-agent requirement, use the existing four-view judgment and label the agent run `未执行`. Do not fabricate agent speech or silently label a single-agent analysis as multi-agent. If the user explicitly required independent debate, save a limitations report for a deep dive with the verified evidence and incomplete status so the analysis can be rerun where the tools are available.

The report contains only decision-relevant claims, responses, risk constraints, and reasons for the final judgment. Do not paste entire agent transcripts or present an agent's confidence wording as a measured probability.

Report three separate states near the top: agent workflow (`完成 / 部分完成 / 未执行`), material evidence gaps, and report/artifact acceptance (`草稿 / 待用户验收 / 完成`). A returned `unresolved` or `evidence_missing` response counts as a response when it identifies the retained claim and explains the sourced disagreement or gap; it does not make the evidence sufficient. Workflow completion cannot close a hard constraint or prove a rating. Conversely, unresolved evidence does not mean a returned round never ran. Use the same states in the header and debate/risk sections, with absent risk roles visible in the header.
