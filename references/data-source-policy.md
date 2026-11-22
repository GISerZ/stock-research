# A-share Data Source Policy

## Source Priority

Use official or primary sources for core conclusions:

1. Shanghai Stock Exchange, Shenzhen Stock Exchange, and Beijing Stock Exchange announcements.
2. CNINFO disclosures: annual reports, semiannual reports, quarterly reports, temporary announcements, and performance forecasts.
3. Company official website and investor relations pages.
4. CSRC, exchange inquiry letters, regulatory measures, disciplinary actions, and supervision letters.
5. Official statistics, ministry policy documents, and industry association data.

Use auxiliary sources for market context and leads:

1. Eastmoney, Tonghuashun, Sina Finance, Tencent Finance, Securities Times, Cailian Press, and comparable finance aggregators.
2. Wind, Choice, Bloomberg, or similar terminals only when available in the user's environment.
3. Xueqiu, stock forums, investor Q&A, and social discussion only as sentiment or clue material.
4. US, Hong Kong, Korean, index, ETF, commodity, currency, and rates data only for cross-market reference.

## Browsing Rules

Always browse for current stock research. Search official sources first when researching financial reports, announcements, shareholder changes, regulatory events, major contracts, buybacks, dividends, pledges, or lawsuits.

## Quantitative Evidence Routes

### Dataset routing and failure contract

| 数据集 | 发布方／聚合方 | 现用访问工具 | 证券覆盖、字段／单位 | 源端时点 | 主备条件与边界 |
|---|---|---|---|---|---|
| 未复权报价 | 腾讯；备源东财（行情聚合） | `evidence_market.py` HTTP：`qt.gtimg.cn` → `push2.eastmoney.com` | 沪深北，CNY/股、交易时间及已确认口径的量额／市值 | 供应商交易时间，另存抓取时间与市场阶段 | 腾讯失败／stale 后尝试东财；两源不能核验时不评级，日历缺失须人工核验阶段 |
| 日线 | 腾讯；备源东财（行情聚合） | AKShare `stock_zh_a_hist_tx` → `stock_zh_a_hist`，原始HTTP页检查 | 沪深先腾讯，北交所东财；约370日窗口，未复权收盘CNY/股、成交股数／CNY | 已完成交易日及日历／缺日诊断 | 腾讯非ok后走东财；重复／倒序、空表不是no_record，不直接排序去重掩盖；停牌／上市缺日另核 |
| 财务与每股指标 | 上市公司披露；新浪三表／东财每股聚合 | AKShare `stock_financial_report_sina`、`stock_financial_analysis_indicator_em` | 合并累计损益／现金流、期末存量CNY；EPS／每股净资产CNY/股，最多8个报告期 | 报告期不等于公布日；重要数据回原披露核时间 | 无自动原文替代源；缺字段不补零，原文核验后采用 |
| 公告与原文 | 公司／巨潮官方披露，交易所复核 | `evidence_disclosure.py` HTTP完整分页；`evidence_documents.py`下载PDF／PyMuPDF文本 | 目标公司两年索引、有界原件及候选页 | 公告公布日，另存下载时间、哈希与PDF页 | 索引失败转交易所人工查；新闻不代替披露，候选未命中不排除事件 |
| 研报索引与EPS | 券商原报告；东财索引聚合 | `evidence_valuation.py` HTTP `reportapi.eastmoney.com` | 目标公司两年索引与原始相对年EPS键；EPS候选CNY/股 | 报告日期、180日／事件重置筛选，财年仍待原文核 | 新浪列表／同花顺聚合EPS仅人工线索；待审partial与访问失败分开，未核EPS不入估值 |
| 个股热度 | 东财平台；同花顺独立平台 | AKShare `stock_hot_rank_detail_em`／`stock_hot_rank_em`；HTTP同花顺热榜 | 目标东财历史排名与当前前100；同花顺仅返回当前榜；单位名 | 历史为来源日期，当前榜只有抓取时刻 | 东财当前榜失败才查同花顺；有效榜外为覆盖外，平台名次不拼接为东财五日序列 |
| 讨论榜与帖子 | 雪球榜单；帖子原作者／所处平台 | AKShare `stock_hot_tweet_xq`；研究者浏览及审核附件 | 返回“最热门”榜位置、原始关注字段；帖子是有选择的小样本 | 榜单抓取时刻；帖子公布／抽样时间 | 失败与not_reviewed各留原状，不换平台补雪球名次，不将关注数当帖子数／看多率 |
| 新闻候选 | 东财检索聚合；原媒体／发布者另核 | AKShare `stock_news_em`；研究者主动浏览原文 | 最近有限条标题／摘要／链接，条数非五日新闻覆盖 | 候选发布时间、盘后标记与抓取时间 | 候选为空不等于没有新闻；重要公司事实回官方披露 |
| 广度与涨跌停池 | 乐咕统计；东财专题池 | AKShare `stock_market_activity_legu`、`stock_zt_pool_em`／`stock_zt_pool_dtgc_em`／`stock_zt_pool_zbgc_em` | 广度沪深上涨／下跌／平盘／停牌家数；三专题池排除ST与科创板 | 乐咕来源统计时刻；池子请求日＋抓取时刻，非源端确认收盘 | 广度只能当天取，历史不回填；三个池分开，空响应不当零，固定版本明确空跌停池例外见下文 |
| 筹码分布与成本估算 | BaoStock行情；东财供应商摘要；本地模型 | BaoStock受限SDK作业＋本地换手衰减；AKShare `stock_cyq_em`备用摘要 | 仅沪深，前复权历史＋末日未复权锚点；成本CNY/股与估算分布 | 实际完整数据日，不等于采集日／当前报价 | 来源失败可降级东财未复权摘要；模型异常保留诊断，摘要无主峰／分布，缺口不自动阻断评级 |

本表描述当前本地适配器的实际路线，不保证接口现在可达，也不穷举候选端点。AKShare是访问工具，AKTools是其服务入口；改换工具而仍访问东财不增加独立上游。表内“发布方／聚合方”不表示聚合数字已核原文，最终以各次`source_results`、实际覆盖和供应商时间为准。

### Reading saved diagnostics

先读单条`status/detail/error_type/http_status/coverage/request_log`，再说明对具体问题的影响。`malformed`说明结构或数值检查未过，不能仅凭计数认定重复、乱序或分页重叠的根因；`source_failure`还须区分连接、超时与HTTP拒绝。418按当前运行时记录为`http_error/source_failure`，不能改写成已确认403/429限流或永久封禁。日线`partial`的缺日可能需要停牌／上市证据解释，不直接认定供应商漏数。

`no_record`需有有效查询或榜外依据；HTTP成功但空body、空表或缺字段不能证明完成了空查询。券商索引成功而EPS为`stale`或待审`partial`，分别限制当前预测使用和原文采用，不等于索引访问失败；有据的研究者模型仍可按估值契约建立。未审核帖子仅限制样本观点，不能推成看空；辅助缺口不自动否决核心研究，核心披露／股本／报价缺口也不因辅助齐全而放行。

`check_source_health.py`只汇总历史保存结果及诊断，不发起实时验活；其失败率包含覆盖不足／过期，旧记录以时间近似分组，不是实时可用率或SLA。保存的冷却时间不证明新进程仍在冷却。本批不改变重试、冷却或统计口径，不反复重启采集；适配修复／独立备源须另记可重现输入、原响应证据、根因与范围后处理。

来源状态在旧 `ok / no_record / source_failure / stale / not_supported` 之外，增加可选的 `rate_limited`（403／429 等限流反爬）、`malformed`（空响应或结构／代码／日期／数值无效）、`partial`（有数据但覆盖不足）。`no_record` 只用于结构有效、完成查询后的明确空结果或有效非空榜单的覆盖外目标。SDK 无法证明空查询完成时应保留 malformed，不推断没有记录。

证据 v1/v2 和情绪 v1 保持原 schema。新来源结果可含 `attempts`、`elapsed_ms`、`http_status`、`error_type`、`retrieved_at`、`coverage`、`fallback_from` 和 `request_log`；旧快照没有这些字段仍按原语义读取。`attempts` 是该结果消耗的实际请求尝试总数，分页总数可超过 3，但每个 HTTP 请求最多尝试 3 次。`request_log` 保留各次 HTTP 状态和错误；不会保存请求头或凭据。备用成功时保留先前失败结果，最终结果另写 `fallback_from` 和实际覆盖；报告同时说明失败主源、最终来源、查询范围及其限制。

请求默认连接／读取超时 `(5, 15)` 秒，只重试网络异常、429 和 5xx，指数退避加抖动；参数／解析错误不重试，403 直接冷却。重试耗尽的网络故障及 403／429 在同一运行时内冷却，普通来源默认 300 秒、辅助情绪至少 900 秒。采集按序执行；不提高并发对抗限流。冷却是进程内状态，重新启动命令不会继承冷却；不要反复重启绕过它。AKShare 函数及其直接调用的 AKShare 辅助函数使用局部绑定的 HTTP facade，不改全局 requests 或 socket。BaoStock 不提供超时参数，使用 45 秒上限的独立 SDK 进程，超时保留诊断结果。

阶段按北京时间记录为 `premarket`（含开盘集合竞价）、`intraday`、`lunch_break`（11:30–13:00）、`closing_auction`（14:57–15:00）、`postmarket`（15:00 起）、`non_trading` 或 `unknown`。是否交易日来自来源日历，不按周一至周五猜测。行情供应商时间与当前阶段分开保留；非交易日可展示最近交易日的价格，但不能称当日成交。日线只在其日期已结束且来源实际提供时有效。代码／前缀不匹配、未来时间、与应有交易日不符、盘中明显延迟或零成交且等于昨收均不能锚定当前评级。

腾讯／东财日线在 SDK 排序与去重前，通过局部 HTTP 回调检查原始分页：目标代码／市场、非空行、日期顺序与重复、字段、价格及成交量额。`coverage.raw_pages_checked` 和 `raw_pagination_verified` 记录实际检查范围；SDK 或注入的适配器未经过已识别的 HTTP 路线时，该标记为 false，不能宣称已验证原始分页。停牌、上市日期或关键趋势有争议时仍须独立复核；升级 SDK 后须重新检查其请求方式、列名及单位。

东财备用报价只补充已检查的价格、时间、成交额和市值，不把未确认口径的东财 PE 字段写成 TTM PE。同行备用报价缺少某个倍数时保留空值；不能由现价反推 EPS 或复制主源失败前的倍数。

报价时效单独核对：`market_phase`仍是采集阶段，`quote_phase`是源端报价时间所属阶段；`freshness_cutoff`只记录本次实际适用下界，未知写null。腾讯第一方[SuperData](https://wzq.gtimg.com/resources/web-quota-page/SuperData_v20260825.js)将第30项定义为TimeStamp、第40项为Status，[行情页脚本](https://st.gtimg.com/quotes/hs-fund/bundle.13362df9.js)将前者放入secu_quote.utime，故按`provider_quote_time`使用，不升级为交易所认证的最后成交或收盘确认。东财第一方[字段与状态实现](https://quote.eastmoney.com/newstatic/build/vendor.js)将f86用作交易时间、f292用作交易状态，按`provider_trading_time`保留；不再把两个已识别来源无条件写成partial。

连续交易/收盘竞价沿用15分钟容忍；午休所需时间不早于11:15，盘后及前一完整日收盘背景不早于15:00。已知源端报价时间落在所需时间段内，且日历、正常交易状态、量额均成立时可ok。**早于午休/盘后下界而缺独立收盘确认的报价**仍保留partial候选、源端阶段unknown和空cutoff，走备源，不将未证实为快照更新时间的字段误判stale。东财f292=5明确表示“已收盘”，在日期和采集阶段适配时作为独立收盘确认，允许保留早于15:00的真实最后成交时点；f292=19等盘后交易状态不能代替该确认。未来5分钟、日期和原15日边界保留；源端正常状态和时效不能由采集日期替代。盘前9:15前沿上一完整日背景，9:15起的当日数据只称竞价背景，f292=10“未开盘”不作有效当日竞价报价。

`coverage`保留raw_quote_time、quote_time_basis、quote_time_evidence、provider_state、可用的provider_phase及close_confirmed。东财状态按第一方枚举适配：2交易中、3午休、4收盘竞价、5已收盘、6/14停牌、10未开盘、12/17—19盘后、13休市；未知/不适配、非正常状态、零活动或缺日历均不产生ok。停牌及稀疏成交保留候选和限制，不能仅因最后成交没到15:00就认定失效。供应商数据可被人工原始来源复核，但本次未运行采集/验收；官方字段使用是适配器依据，不是服务永远准确的保证。

同行仅在目标与同行**实际被选来源**均为时效已核`ok`、同交易日且采集阶段适配时可比，并互核时效窗口。某侧已有独立收盘确认时，不再用另一侧快照更新时间下界误拒其较早的真实最后成交时间；这不豁免日期/阶段及ok门槛。旧快照或调用方未提供目标来源诊断时保持不可比。不得仅靠两个观察项日期/阶段相等提升可比性。旧文件缺这些可选字段代表未知，不补成已检查。

筹码是独立 `kind=chips`、schema v1 附件，原证据/情绪 schema 不变。`baostock_chip_history` 查询及价格基准校准、`akshare_chip_summary` 降级和解释边界见 `chip-analysis-framework.md`。BaoStock 的 `attempts=1` 表示一次受限 SDK 作业，不是逐页底层 socket 请求数；HTTP 路线仍按实际请求日志计数。筹码 `collection_status` 只描述采集/模型覆盖，不代表投资有效性；参考收盘价不能替代当前评级报价，均成本偏离不能当安全边际。保留固定 AKShare 的 P50 方法标记，不能与加权均成本混用。

For a single-stock deep dive, first run `scripts/collect_evidence.py` with a working Python interpreter from the current workspace. The command saves a versioned `research/evidence/YYYY-MM-DD-<code>.json` snapshot with quote, daily bars, historical valuation, financial statements, per-share figures, the complete two-year CNINFO index, selected official PDFs and extracted text, broker report EPS leads, and explicitly selected peer snapshots. A new same-day run receives a `-v2` suffix instead of replacing the prior snapshot. Use the packet's per-source status and `issues` to decide what needs independent retrieval. Its `retrieved_time` is collection time; `period_or_market_time` is the provider's trading or reporting time. Structured financial values are unverified until reconciled to the original filing. Extracted PDF passages are page-linked candidates and require reading the original disclosure before conclusions.

| No-key collector route | Coverage and role | Limit |
|---|---|---|
| Tencent single-stock quote | Shanghai, Shenzhen, Beijing; unadjusted price and provider time plus vendor PE/PB leads | A stale or zero-activity quote cannot anchor a current rating. |
| AKShare Tencent daily bars, with Eastmoney fallback | Shanghai and Shenzhen use Tencent first; Beijing uses Eastmoney; one-year unadjusted price, shares traded, and amount | Eastmoney connectivity can fail; report `source_failure` and use a separate source before drawing a trend conclusion. |
| BaoStock daily history | Shanghai and Shenzhen: five-year PE/PB/PS/PCF, turnover, trading status, ST flag | Beijing is `not_supported`; historical multiples are vendor data, not fair values. |
| AKShare Sina consolidated statements | Eight report periods of income, balance sheet, and cash flow with cumulative/period-end basis | Field availability varies by sector; missing values stay missing and all figures require original-filing checks. |
| AKShare Eastmoney per-share indicators | Basic EPS and book value per share by report period | Aggregated values remain `unverified`; do not back-solve EPS from price and PE. |
| CNINFO official index and selected PDFs | Complete two-year index, official PDF URLs, bounded downloads, text and page-linked candidate passages | Full pagination must match; a missing text match is not proof that an event did not occur. |
| Eastmoney broker report index | Two years of report metadata and raw relative-year EPS fields | Missing, old, and pre-event forecasts cannot be treated as current company guidance. |
| Explicit Tencent peer quotes | Timestamped peer price, PE/PB, and market cap for analyst-selected codes | Quote date and market phase must match the target before a same-time comparison. |

BaoStock历史估值先暂存，逐行及迭代结束后检查错误码；明确错误时不发布部分行。worker传回实际日期，父层合并coverage而非覆盖，按已核日历检查请求窗口首、中、末，保存`first_date/last_date/bars/gap_dates/latest_complete_trade_date/history_coverage/iteration_status`后移除内部日期列表。仅请求窗口完整覆盖才记ok；日历失败、短历史、缺日、零码提前结束或空查询未证实均记partial，不能称完整五年。上市/停牌解释须另有证据，不用工作日猜测；负PE/PB不删。45秒SDK进程上限、北交所not_supported及独立logout诊断保留。此路线没有足够证据认证正常空结果，故不凭零行写no_record。

腾讯原页页内重复/倒序仍拒绝；跨页仅同日OHLC/量额一致允许，冲突带日期并走备源。仅实际核过腾讯原页时，对SDK合表最终消费的date/OHLC/volume/amount同值行收敛，避免辅助turnover差异保留合法重叠；未知路线不做该收敛。第一方原页表明年度param请求可能返回起点以前的滚动约640条数据，因此不把原始页起止强行等同请求窗口；SDK整理后的唯一日、370日目标窗口和日历仍严格核对。东财检查不放宽，跨页映射只活在本次闭包。

第一方[腾讯行情页脚本](https://st.gtimg.com/quotes/hs-fund/bundle.13362df9.js)对普通A股使用100、GP-A-KCB使用1的量单位因子；本次取得sz000001、普通深市及科创板原量额作为对照。sz000001的2026-11-11原量1057038手、原额124534.14万元，与11.70—11.86元价格口径一致。用户site的AKShare1.18.97源码确实把sz000排除在手转股之外。实现不再盲信版本/前缀的SDK输出：仅该漏换算路径逐日核SDK量等于原量或原量×100，并核SDK额等于原额×10000，再以原量×100统一成股；SDK已转股时不再乘一次，其他板块保持原处理。不匹配拒绝；未知HTTP路线仍partial省略未核量、走原备源，这是运行保护而非待实现子项。

新采集的日线coverage记录实际python_executable、adapter_module、adapter_path、volume_unit_verified、volume_rows_corrected及volume_basis/evidence；不靠旧虚拟环境路径推断实际运行模块。旧包缺字段仍是未知，不回写。原始材料与读取时点在工作区第二轮计划第16节；只下载材料，没有运行采集器或历史失败重放。

### Financial statement candidates

新浪三表的已识别原始HTTP路线须核paperCode/source/type、合并主体及rCurrency，再把选中八期项目序列与SDK**最终采用列名的那一期**（可能更早）核对。项目增删/调序、重复名不同值、期间/类型/币种错配拒绝该报表，其他独立来源继续保留。原路线未识别时记partial，数值只留字段诊断为未核候选，不输出未经币种/对齐确认的CNY观察。

`coverage.field_diagnostics`按period/field/state/raw_name/reason区分matched、mapping_missing、source_field_missing、source_value_invalid、alignment_unverified。matched只证明原始项目/SDK列名/币种已对齐，金额仍为unverified。缺失、空值、非法值不能补0，真实0与负收益保留。capex已有映射；缺值不能称“未实现”，未取得原表头证据不添加猜测别名。健康摘要最多列12条字段问题及总数；旧文件缺诊断保持未知。没有默认保存完整原响应或重写历史候选包。

`scripts/evidence_financial.py` maps the following additional fields from the existing AKShare Sina statement route. Income and cash-flow amounts retain the consolidated cumulative basis; balance-sheet amounts retain the consolidated period-end basis. Each statement keeps up to eight distinct report dates, which need not supply every desired comparison period.

| Observation field | Sina item title | Statement / basis |
|---|---|---|
| `operating_cost` | 营业成本 | Income / cumulative |
| `investment_income` | 投资收益 | Income / cumulative |
| `fair_value_income` | 公允价值变动收益 | Income / cumulative |
| `accounts_receivable` | 应收账款 | Balance sheet / period-end |
| `inventory` | 存货 | Balance sheet / period-end |
| `short_term_borrowings` | 短期借款 | Balance sheet / period-end |
| `current_noncurrent_liabilities` | 一年内到期的非流动负债 | Balance sheet / period-end |
| `long_term_borrowings` | 长期借款 | Balance sheet / period-end |
| `capex_cash_paid` | 购建固定资产、无形资产和其他长期资产支付的现金 | Cash flow / cumulative |

These candidates preserve the provider amount as CNY, report date, matched title in `basis`, source URL, retrieval time and `verification="unverified"`; they do not establish a publication time. Finite negative income or cash flow remains signed. Missing, blank, non-numeric and non-finite values produce field/period issues without a zero observation; an explicitly reported numeric zero remains zero. A source result of `ok` does not establish full field coverage or original-filing verification. Keep statement failures separate and retain available observations from other statements.

Match the item itself: 营业总成本 cannot replace 营业成本; 应收票据及应收账款 cannot replace 应收账款; investment income, cash received from investments and net investing cash flow cannot replace one another or `capex_cash_paid`. These nine additions do not provide complete debt, unrestricted cash, non-recurring items, minority interests or share-event accounting. Use original disclosures and the optional review tables in [research-workpaper.md](research-workpaper.md) for material gaps; no new provider or automatic net-cash/solvency conclusion is implied.

Choose sources by the claim being tested, rather than collecting every available indicator:

1. **Company facts and financial statements:** use the original exchange or CNINFO disclosure as the primary record. Structured financial series from AKShare, BaoStock, or an available Tushare account can speed comparisons, but reconcile material figures and publication dates with the filing.
2. **Price, volume, and valuation snapshots:** use a timestamped A-share quote or daily-bar source such as Tencent or a documented AKShare adapter; use an independent source when the quote is stale, the ticker changed, or the number drives the conclusion. Record exchange, trading date or time, currency, price-adjustment mode, and whether a ratio is TTM, forecast, or fiscal-year based.
3. **Industry and macro context:** use exchange, index-provider, People's Bank of China, National Bureau of Statistics, or industry-association releases when the metric actually explains the company's business. State the causal link rather than attaching unrelated market statistics.
4. **Events and risks:** use official announcements for pledges, shareholder changes, buybacks, lockups, litigation, and regulatory actions. Aggregator event lists are discovery aids until the original announcement is checked.
5. **Broker reports, news, fund flow, and social signals:** use these for forecasts, consensus, or sentiment context. Label estimates as estimates and do not treat a vendor's EPS field as an official company forecast. Check the report date, original PDF where available, and any material event that invalidates its pre-event earnings basis.

When the Eastmoney broker-report route returns `no_record` or `source_failure`, a researcher may manually consult the Sina research-report list for title, institution, author and report date, then locate the original report; that list does not supply EPS. The Tonghuashun aggregate EPS view is a separate lead, but its figure is **not usable broker EPS** until the relevant fiscal year, report date, contributing coverage and original report can be checked. Neither route automatically fills `broker_reports` or `valuation_gaps`; keep the original Eastmoney status, and do not copy an unverified aggregate or an old pre-event forecast into valuation inputs.

For key report numbers, preserve `value`, `unit`, `period/as_of`, `publication_time` when available, `retrieved_time`, `adjustment_or_calculation_basis`, and a direct source link. Distinguish `no record`, `source failure`, `stale`, and `not supported`; never silently substitute one for another. If a crucial number cannot be reconciled, disclose the conflict and withhold a strong rating.

New broker-index records expose `candidate_for_manual_review`; `usable_for_current_valuation` remains false because the collector does not verify report originals, explicit fiscal years or share bases. `broker_forecast_eps=partial` means current leads were retrieved but that verification is pending; it is not a failed index query. `eps_relative_years` retains raw vendor keys rather than assigning fiscal years. Old snapshots may have `usable_for_current_valuation=true`; read that as a legacy recency filter, not completed original-report verification. Follow `valuation-framework.md` before using forecasts or their median in a report, and retain the manual verification in the report without rewriting snapshots.

Core `collected_at` is collection start; new packets additionally carry `collection_completed_at`. Quote requests advance the supplied run reference by elapsed collection time, so peer/fallback quotes do not use the run's stale start clock for phase/freshness checks. Use each quote's own `retrieved_time`, provider time and source request metadata. Non-quote observations can retain an adapter batch reference time; inspect source-level `retrieved_at` and request logs for actual request timing. Record an explicit `research_as_of` when freezing a brief, including separately verified originals and supplements; neither collection start nor end automatically defines that information cutoff.

The bounded PDF selection includes four recent full periodic reports, the latest available performance/share-basis/risk notices by category, and transaction candidates, after explicitly requested documents. The limit and skipped-document list still apply; selection is not a complete material-event review. Search the official index and manually open additional relevant originals when needed.

## PDF Section Candidates

Readable documents may carry optional `section_candidates` for restricted cash, receivables aging, related parties, commitments/contingencies, non-recurring items, management discussion and subsidiaries/minority interests. These are keyword navigation leads with `verification="candidate"`, separate from transaction `excerpts`. Open the linked official PDF at the candidate's 1-based PDF page before adopting any fact; confirm table headers, units, period, entity and context on the original page. A restricted-asset hit is not necessarily restricted cash, and an aging hit may concern another receivable. Only after original-page verification may a number enter the workpaper's verified inputs, with its source and basis recorded.

Heading-based ordering prefers relevant body/notes over detected contents and accounting-policy pages; it does not certify the section or the hit. PDF position can differ from printed page labels: record printed pages only when actually read, without inferred offsets. `extraction_status=ok` means some text was extracted, not that all pages were readable or finances verified. Read partial-text issues; `text_unavailable`, an empty candidate list, or a legacy document without this field never establishes absence of disclosure or risk. See `collection-and-storage.md` for the field and preservation rules.

## Sentiment Evidence And International References

The separate `scripts/collect_sentiment.py` snapshot is supporting evidence for crowding and short-term expectations. The 18:00/20:00 Windows task captures only domestic market data; stock news, reviewed posts and selected international references are gathered during research. Preserve source observation, publication, availability and retrieval times, market scope, units, calculation basis, direct URL, status and the exact saved snapshot path. Five-day changes require five valid points under the same definition and each market's trading calendar. Do not backfill a missed source day or treat `null` as zero.

| Source | Use and limit |
|---|---|
| [AKShare / 乐咕市场活跃度](https://akshare.akfamily.xyz/data/stock/stock.html) | `stock_market_activity_legu` yields a current 沪深 breadth table with a source statistics time; it has no reliable historical backfill. Reject intraday or wrong-date data as a closing snapshot. |
| [AKShare / 东财涨停池、跌停池、炸板池](https://akshare.akfamily.xyz/data/stock/stock.html) | `stock_zt_pool_em`, `stock_zt_pool_dtgc_em`, `stock_zt_pool_zbgc_em` are separate date-queried topic pools with limited recent coverage. The topic excludes ST and STAR stocks; the limit-up pool also excludes new stocks with uninterrupted one-price limit-up boards. Do not present their counts as all-A-share totals or directly compare them with STAR names. In pinned AKShare 1.18.97, an empty down-limit frame means an explicit empty pool; the other two wrappers also return empty frames when source data is unavailable, so their empty frames do not prove zero. |
| [AKShare / 东财人气榜](https://akshare.akfamily.xyz/data/stock/stock.html) | `stock_hot_rank_detail_em` supplies recent historical target ranks; filter non-trading days. `stock_hot_rank_em` covers the current top 100 only; absence is outside coverage, not rank zero. |
| [同花顺 A 股当前热榜](https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock?stock_type=a&type=day&list_type=normal) | Consulted only when the Eastmoney current top-100 route fails. Save its rank under `ths_current_heat_rank` with its own source result, returned-list scope and retrieval-only time. It is not a substitute for Eastmoney or Xueqiu rank and cannot fill the Eastmoney five-day sequence. |
| [AKShare / 雪球讨论榜与东财新闻](https://akshare.akfamily.xyz/data/stock/stock.html) | `stock_hot_tweet_xq` preserves its raw “关注” field and list position, not post counts or bullish share. `stock_news_em` yields a limited recent candidate list; open important originals and verify material facts with official disclosures. |
| [Nasdaq SOX](https://indexes.nasdaq.com/Index/Overview/sox), [NDX](https://indexes.nasdaq.com/Index/Overview/NDX), and selected overseas peers | Use only when product, customer or supply-chain links make the comparison meaningful. Match completed market sessions and price-adjustment basis. A peer's price action does not verify the A-share company's earnings. |
| [Cboe volatility indices](https://www.cboe.com/us/indices/indicesproducts/) and [put/call statistics](https://www.cboe.com/data/mktstat.aspx) | VXN is Nasdaq-100-related implied volatility; distinguish it from VIX and label total, equity, index or ETP put/call scope. Neither measure alone establishes direction for the target stock. |
| [US Treasury nominal](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve) and [real yields](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve) | Specify tenor and measure changes in basis points; use only for a clear discount-rate or financing channel. |
| [CME FedWatch](https://www.cmegroup.com/fedwatch), [Federal Reserve decisions](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | FedWatch is a futures-implied, model-dependent distribution for a specified FOMC meeting, not a Federal Reserve promise. Compare probability changes only for the same meeting and outcome; use Fed originals for actual decisions. |
| [ICE BofA US high-yield spread via FRED](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) | Optional broad credit-stress reference; it does not directly measure an A-share firm's borrowing cost. Check release timing and available history. |
| [EIA WTI/Brent spot](https://www.eia.gov/dnav/pet/PET_PRI_SPT_S1_D.htm) and relevant commodity or FX sources | Record spot/futures, contract or grade, unit, currency and publication lag. Include only with a demonstrated cost, revenue or translation channel. |

Social-post review requires a direct post link, target, publication time, summary and selection method; it cannot estimate the whole investor population from a small sample. ETF share changes and fund flows remain candidate leads when the original scope or publication time is unclear. Financial filings, AI capital spending, foundry sales and chip prices are industry or fundamental evidence rather than pure sentiment readings. Sentiment cannot relax the no-rating gate for missing latest material disclosure, share basis or timestamped quote.

Check current documentation before programmatic use: [AKShare stock data](https://akshare.akfamily.xyz/data/stock/stock.html), [Tushare permissions](https://tushare.pro/document/1?doc_id=108), [CNINFO disclosures](https://www.cninfo.com.cn/new/commonUrl?url=data/gongkai), and [Shanghai Stock Exchange](https://www.sse.com.cn/). These references describe available routes, not a guarantee that any endpoint remains reachable.

For each important factual claim, record the source type:

- `官方披露`: exchange, CNINFO, company, regulator, official statistics.
- `市场数据`: quote, valuation, index, sector, fund-flow, or volume source.
- `媒体报道`: news and finance media.
- `市场情绪`: forum, social platform, investor Q&A, or discussion board.
- `模型推断`: reasoning derived from sourced facts.

## Conflict Handling

When sources conflict:

1. Prefer official disclosure over media.
2. Prefer timestamped filings over summary pages.
3. Prefer original data tables over screenshots or reposts.
4. State the conflict plainly in the report.
5. Downgrade conviction when the conflict affects rating, valuation, or position advice.

## Evidence Rules

Do not use forum sentiment as primary evidence.

Do not support a buy conclusion with one news article.

Do not infer an undisclosed financial figure from price action or sentiment.

When the latest material filing or a timestamped current quote cannot be verified, mark the report `数据不足，暂不评级` and omit numeric trading ranges.

When using overseas or cross-market references, explain the mechanism: same industry, supply chain, customer demand, commodity input, policy spillover, valuation mapping, or global risk appetite.
