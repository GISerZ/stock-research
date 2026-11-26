# stock-research 使用与文件说明

本目录是一个面向 **A 股研究**的 Codex skill。入口是 [SKILL.md](SKILL.md)：它规定何时调用本 skill、证据核验顺序、评级与价格区间的门槛，以及完整报告的保存规则。本文面向维护者和使用者，说明目录中各文件的职责及手动使用方法；实际研究时仍以 `SKILL.md` 和相应参考文件为准。

该 skill 可处理单股深度研究、估值和同业比较、买入／持有／风险判断。港股、美股、韩股、指数、商品和宏观数据默认只作为有明确传导关系的参照。工具会收集线索并保存证据，但**不会自动核实所有数字、生成评级、计算价格区间或下单**。重大事实与财务数据要回到原始公告核对。

默认研究从估值基准日起未来12个日历月，写清起止日期，以期末低／基准／高情景价值和相对参考报价涨跌空间为主，并跟踪年内关键经营节点；用户指定周期优先。估值财年、财年模型价值、期末情景价格和当前操作价带分别说明，模型空间不冒充一年预期收益。仅报价或辅助补件不顺延原终点；重新采用未来一年窗口按模型变化另存决定。历史报告和前瞻登记保留原期限，不批量迁移。具体口径见[底稿](references/research-workpaper.md#研究期限与期末情景)及[估值框架](references/valuation-framework.md#horizon-and-terminal-value)。

## 目录结构与职责

简短公告/事实、聚焦情绪和纯筹码补件按问题回答，不强制评级；一旦提供投资评级，原文、实际股本、带时点报价、模型和价带门槛全部保留。单股筹码专节、按要求保存及已有总览义务不变；用户要求完整但证据不足的研究仍保存限制性报告。发布前复用run-record最终采用栏集中核对版本与实际时间，不预填未来落款，不新增状态清单。

| 路径 | 作用 |
| --- | --- |
| [SKILL.md](SKILL.md) | Codex 的主指令：适用范围、按任务类型加载参考文件、研究流程、独立 Agent 辩论、评级门槛和报告保存约定。 |
| [agents/openai.yaml](agents/openai.yaml) | 在 Codex 界面显示的名称、简介和默认示例提示。 |
| [requirements-evidence.txt](requirements-evidence.txt) | 证据采集脚本使用的固定版本 Python 依赖。 |
| `references/` | 研究判断和写作规则。详见下表。 |
| `scripts/` | 采集、保存和定时运行的实现。详见下表。 |
| `tests/` | 现有脚本测试及价格区间案例资料；日常使用 skill 无需直接调用。 |
| `.venv/` | 当前机器上的本地 Python 环境。路径和解释器可能随机器变化，不应当作可移植的 skill 资源。 |

### 参考文件

| 文件 | 何时阅读 |
| --- | --- |
| [data-source-policy.md](references/data-source-policy.md) | 采集前阅读。规定官方披露优先级、各数据源用途、时间和口径、冲突处理。 |
| [collection-and-storage.md](references/collection-and-storage.md) | 执行采集和保存前阅读。集中列出命令、故障诊断、来源状态、精确版本、链接和保存规则。 |
| [a-share-research-framework.md](references/a-share-research-framework.md) | 深度报告、行业比较或复杂判断时阅读。给出公司、财务、行业、估值、市场、催化剂和风险的分析顺序。 |
| [valuation-framework.md](references/valuation-framework.md) | 讨论合理估值、目标区间或同业比较时阅读。说明估值方法选择、情景计算和安全边际。 |
| [position-building-and-risk.md](references/position-building-and-risk.md) | 输出评级、分批计划或风控条件前阅读。规定五档评级与价格区间的对应要求。 |
| [sentiment-framework.md](references/sentiment-framework.md) | 单股深度研究或情绪问题时阅读。规定快照、国内外消息主动检索、预期变化卡、心理假设与反证、板块量价验证、帖子审核及跨市场口径。 |
| [chip-analysis-framework.md](references/chip-analysis-framework.md) | 单股深研或筹码/成本专题时阅读。规定筹码模型、摘要降级、时间/价格基准、指标和研究判断边界。 |
| [follow-up-workflow.md](references/follow-up-workflow.md) | 更新已有股票研究或深度研究发现前次完成报告时阅读。规定旧报告、证据版本、价带失效条件和变化表。 |
| [decision-exchange.md](references/decision-exchange.md) | 未来确定外部消费端时参考的机器交换字段契约；目前没有导出器或项目接入。 |
| [multi-agent-debate.md](references/multi-agent-debate.md) | 单股深度研究或明确要求独立辩论时阅读。规定共同证据摘要、多空回应、三方风控和未完成状态。 |
| [report-template.md](references/report-template.md) | 写完整报告前阅读。是报告结构模板，不能把空模板当成已完成研究。 |

### 脚本

| 文件 | 作用 |
| --- | --- |
| [collect_evidence.py](scripts/collect_evidence.py) | 命令行入口。采集单股行情、财务、公告、选定公告 PDF、券商预测线索及选定同业，保存 schema v2 证据包。 |
| [evidence_core.py](scripts/evidence_core.py) | 股票代码识别、证据包字段校验和同日版本化保存。 |
| [source_runtime.py](scripts/source_runtime.py) | 来源请求的超时、有限重试、冷却、尝试日志与来源链；不改全局 requests／socket。 |
| [market_phase.py](scripts/market_phase.py) | 北京时间交易阶段及来源实际提供的已完成日线日期。 |
| [evidence_market.py](scripts/evidence_market.py) | 报价、历史 K 线和历史估值数据。 |
| [evidence_financial.py](scripts/evidence_financial.py) | 财务报表及每股指标的结构化候选值。 |
| [evidence_disclosure.py](scripts/evidence_disclosure.py) | 巨潮资讯公告索引。 |
| [evidence_documents.py](scripts/evidence_documents.py) | 选取、下载公告 PDF，提取带页码的文本候选段落。 |
| [evidence_valuation.py](scripts/evidence_valuation.py) | 券商报告线索、可比公司快照和估值缺口记录；不直接生成评级。 |
| [collect_sentiment.py](scripts/collect_sentiment.py) | 命令行入口。采集当日市场或单股情绪快照。 |
| [collect_chips.py](scripts/collect_chips.py) | 独立筹码入口，保存完整日的本地分布或明确摘要/失败诊断。 |
| [evidence_chips.py](scripts/evidence_chips.py) | 45 秒 BaoStock worker、复权锚定和 AKShare 摘要降级。 |
| [chips_core.py](scripts/chips_core.py) | 三角分布/换手衰减、成本指标、生产快照校验、版本化 JSON 与 SVG。 |
| [check_sentiment_coverage.py](scripts/check_sentiment_coverage.py) | 只读检查最近完整交易日的市场快照和近五日逐字段有效覆盖，不采集或改写文件。 |
| [sentiment_core.py](scripts/sentiment_core.py) | 情绪快照校验、去重／版本化保存和市场近五日快照读取。 |
| [sentiment_market.py](scripts/sentiment_market.py) | 市场广度及涨停、跌停、炸板等专题池。 |
| [sentiment_stock.py](scripts/sentiment_stock.py) | 个股热度、东财失败时独立记录同花顺当前热榜候选、讨论榜、新闻候选及人工帖子审核结果。 |
| [sentiment_cross_market.py](scripts/sentiment_cross_market.py) | 研究者选定的海外／宏观参照及其时间、口径校验。 |
| [create_report.py](scripts/create_report.py) | 默认更新 `.drafts/` 中同一草稿；显式 `--publish` 先预检后原子发布；原样重试复用，真实更新/发布后更正另存带原因的新版本。 |
| [validate_report.py](scripts/validate_report.py) | 只读核对元数据、相对链接、JSON 契约、代码、行情时间、评级价带及跟踪报告引用。 |
| [check_source_health.py](scripts/check_source_health.py) | 只读汇总所有版本快照的来源状态、最近成功／失败时间、覆盖范围和建议动作。 |
| [install_sentiment_schedule.ps1](scripts/install_sentiment_schedule.ps1) | 可选：为当前已登录 Windows 用户注册每日 18:00、20:00 的市场情绪采集任务。 |
| [run_sentiment_schedule.ps1](scripts/run_sentiment_schedule.ps1) | 定时任务实际调用的包装脚本，记录 `schedule.log` 和退出码。 |

## 环境准备

在要保存 `research/` 的工作区打开 PowerShell。选用可用的 Python 解释器，按需安装本目录的依赖：

```powershell
$stockSkill = Join-Path $env:USERPROFILE '.codex\skills\stock-research'
python -m pip install -r (Join-Path $stockSkill 'requirements-evidence.txt')
```

依赖清单目前固定 `akshare`、`baostock`、`requests`、`pandas` 和 `pymupdf` 的版本。`python` 应指向已安装这些包的解释器；目录里的 `.venv` 只代表本机现状。采集访问外部数据源，需要网络和可用的上游接口。命令中的 `--output-dir .` 表示将结果写到**当前工作区**，不是 skill 目录。

## 典型使用流程

### 1. 收集单股证据

```powershell
python (Join-Path $stockSkill 'scripts\collect_evidence.py') --code 600519 --output-dir .
```

有经过核实的可比公司时，可重复添加 `--peer '代码=可比理由'`。只有在已核实的重大事件使旧预测失去可比性时，才使用 `--valuation-reset-date YYYY-MM-DD`。`--document-url` 只接受该公司巨潮公告索引中的官方 PDF 地址；`--max-documents` 控制最多下载的公告数量，允许 1–100，默认 24。

脚本打印保存的绝对路径。证据包即使部分来源失败也可能保存；**退出码 0 仅表示至少一个研究来源成功**，不能代替逐项阅读 `source_results`、`issues`、`valuation_gaps`。

### 2. 收集市场和个股情绪

交易日北京时间 15:00 后，可手动保存当天已完成交易日的市场快照：

```powershell
python (Join-Path $stockSkill 'scripts\collect_sentiment.py') --market --output-dir .
```

然后为研究标的采集个股快照：

```powershell
python (Join-Path $stockSkill 'scripts\collect_sentiment.py') --code 600519 --output-dir .
```

个股命令可选 `--social-review-file 路径` 和 `--cross-market-file 路径`，分别导入研究者人工核对的帖子和跨市场参照。两个文件均为 UTF-8 JSON；字段要求和示例见 [sentiment-framework.md](references/sentiment-framework.md)。未提供时会保留 `not_reviewed` 等缺口状态。**个股命令即使快照为 `partial` 也可能返回退出码 0**，须阅读 JSON 内的 `completeness`、`source_results` 和 `issues`。

新个股CLI另在保存前写入可选`analysis_coverage`：东财热度有效日／所需5日、市场七字段各自的有效日／缺日、已保存新闻候选数及`candidates_only`、帖子原审核状态、海外原selection状态。它解释可用范围，不升级原始`partial`或认证事实；日历失败／旧字段缺失以不可用窗口、`missing_fields`及null计数说明。旧快照没有摘要仍可按原字段阅读，不回写补齐；新增人工审阅附件不改变旧快照。报告分别说明“能支持什么、缺什么、是否实质影响核心模型”，不能由辅助缺口自动暂不评级，也不能因辅助齐全放宽原文、实际股本和报价门槛。字段定义见 [collection-and-storage.md](references/collection-and-storage.md)。

深度研究还须主动浏览近期公司、板块／产业链及有关联的海外消息，按“消息 → 叙事 → 预期变化 → 心理假设 → 量价验证”保存 `research/evidence/manual/YYYY-MM-DD-CODE/narrative-review.md`，同日更新另存 `-vN`。其中记录原文和可获得时间、检索范围、独立事件、预期参照、样本与反证、同期板块反馈和下一观察点；报告给出独立的短期情绪置信度。这由研究者完成，不要求用户手工喂文件；不是新增的自动资讯管道。附件与既有 JSON 状态分别披露，不补写旧快照，细节见情绪框架。

东财当前前100热榜 `source_failure / rate_limited / malformed / stale` 时，脚本会尝试同花顺 A 股当前日榜，并只在 `ths_current_heat_rank` 中保存匹配名次、返回榜单大小、来源 URL 和抓取时刻。空榜／结构异常记 `malformed`，请求错误按运行时分类；仅有效非空榜单查无该股才记 `no_record`。东财原始失败状态和 `partial` 均保留；同花顺名次不能填入东财五日历史，也不能与雪球或东财名次直接相减。

市场快照只采集当前已完成的交易日；某些市场广度数据无法事后可靠补录。近五日判断只使用实际可用且同口径的有效点，缺日应写明，不能以零值或次日数据填补。

18:00／20:00定时任务是完成日采集与补缺。若当日已有`complete`，市场CLI直接返回原精确版本路径，20:00通常不会重新取数或跟踪源端修订；缺失／partial才进入采集，定时覆盖检查另行执行。没有新增强制刷新参数，也未修改调度。任务已配置不代表本轮实际执行过或来源现在可用。

新个股快照的`market_five_days[].snapshot_path`和`market_snapshot_paths`采用同一精确版本的**工作区相对路径**，基准是已解析的`--output-dir`，例如`research/evidence/sentiment/market/YYYY-MM-DD-v2.json`；统一使用`/`，缺日均保留`null`。读取时从工作区定位，不能从个股JSON所在目录拼接。报告直接保存在`research/`时，Markdown链接改用**报告相对路径**`evidence/sentiment/market/YYYY-MM-DD-v2.json`。采集CLI打印的已保存文件位置仍为**绝对路径**，市场命中已有complete快照的提前返回分支也相同。

旧内部绝对引用仅在目标仍属于指定工作区且文件存在时继续可读；Windows下保留旧反斜杠的读取。`../`越界、其他根目录及缺失文件仍报错。迁移后指向旧盘／旧目录的历史绝对引用应披露无法定位，不自动改写JSON或猜测新根目录；新相对引用随工作区迁移时仍须保留内部目录结构和精确版本。迁移、拒绝错误路径及含空格目录的运行效果由用户在独立副本亲测，静态读回不代表验收通过。

检查已保存市场快照的健康度，不触发采集：

```powershell
python (Join-Path $stockSkill 'scripts\check_sentiment_coverage.py') --output-dir .
```

命令输出最近完整交易日、实际选用的 JSON 版本，以及近五个交易日每项指标的有效天数和缺日；摘要中的`market_days[].snapshot_path`和`latest_snapshot_path`也以工作区为基准，使用上述相对路径，区别于采集CLI的绝对路径输出。退出码 `0` 表示最近交易日 `complete`，`1` 表示最近交易日缺失或 `partial`，`2` 表示交易日历或读取失败（`calendar_unavailable` 时不会猜测工作日）。过去四日无法补采的乐咕广度只在缺口中显示，不使今天已完整的快照永久报警。

### 3. 核验并撰写报告

单股深研还需采集独立筹码附件：

```powershell
python (Join-Path $stockSkill 'scripts\collect_chips.py') --code 600519 --output-dir .
```

筹码专题可单独运行该命令。输出在 `research/evidence/chips/`，文件名按采集日，同日加版本；JSON 内数据日可能是此前完整日，盘中不计算未完成日线。退出码 0=完整新鲜本地模型，1=部分/仅摘要/不支持，2=失败；查看 `data_mode`、`source_results`、`issues` 和 `chart_path`。只在本地模式画图，摘要不补主峰。主峰、均/中位成本、70/90 区间和获利比例都是估算，不是主力账户成本或估值价带；筹码缺失不自动否决研究判断。公式和局限见 [筹码框架](references/chip-analysis-framework.md)。

打开原始巨潮或交易所披露，核对关键财务数值、报告期、公告日期、股本口径及重大事项。行情要记录未复权价格、币种、供应商交易时间和交易阶段。把事实、市场解读、模型推断及尚未解决的冲突分开写，并给关键数字附直接来源。

完整报告按 [report-template.md](references/report-template.md) 填写。只有最新重大披露、股本口径和带时间戳的现价均可核实时，才考虑评级与价格区间；否则写“数据不足，暂不评级”，不编造数值区间或仓位。正向评级须说明持有期限、低／基准／高情景、买入与持有区间公式、安全边际、减持／重估条件和失效事件。

更新已有标的时，按 [follow-up-workflow.md](references/follow-up-workflow.md) 先确定上一份**完成**报告（按日期和同日版本，不只看修改时间），读其实际引用的证据版本，再以本次研究截止时间的公告、股本、财务基数、报价和风险核对旧假设。报告头部写旧报告与新旧证据的精确路径；核心结论后只列会改变判断的“与前次报告相比”表。`仍有效` 仅指旧前提暂未被新证据推翻，不承诺股价或收益；触发旧失效条件则标 `需重算`，旧价带不能沿用。首次研究省略这张表。恩捷股份旧报告有附条件价带，贵州燃气旧报告未设置行动区间；跟踪时均以各自原文为准。

当东财券商研报为 `no_record` 或 `source_failure`，可依 [data-source-policy.md](references/data-source-policy.md) 人工查新浪研报列表定位标题、机构和日期，再寻找报告原文；同花顺聚合 EPS 在未核原文、财年和报告日期前也只算线索，不导入可用券商预测。

单股深度研究按 [multi-agent-debate.md](references/multi-agent-debate.md) 记录实际运行的独立多空辩论与三方风控；若运行环境没有相应能力或某回合未完成，应明确标记，不补写 Agent 发言。

### 4. 保存已完成报告

将完成的 Markdown 先存为 UTF-8 文件，再运行：

```powershell
python (Join-Path $stockSkill 'scripts\create_report.py') --code 600519 --name 贵州茅台 --date 2026-09-29 --output-dir . --content-file 'D:\path\to\completed.md' --validate
python (Join-Path $stockSkill 'scripts\create_report.py') --code 600519 --name 贵州茅台 --date 2026-09-29 --output-dir . --content-file 'research/.drafts/2026-09-29-600519-贵州茅台.md' --publish
```

第一条命令保存/预检可编辑草稿，修复时重复执行不会增加正式版本；第二条在人工核对后显式发布，并自动先做结构和本地引用预检。预检失败退出1，只有`.drafts/`草稿；原样发布重试复用已有版本。真实更新或发布后更正传`--change-reason '具体原因及影响' --supersedes 'research/前版精确文件.md'`，保留前版，同日按数字最大版本递增，跨日保存新日期。参数/存储失败退出2。脚本不采集、联网、分析、验证财务真伪或代替用户验收。省略正文只能生成模板草稿，不能发布。详见[完整发布规则](references/collection-and-storage.md#editable-draft--explicit-publication)。

## 产物与状态

| 产物 | 默认路径（相对 `--output-dir`） | 版本规则 |
| --- | --- | --- |
| 单股证据包 | `research/evidence/YYYY-MM-DD-CODE.json` | 每次另存同日版本 `-v2`、`-v3` 等。 |
| 已下载公告 | `research/evidence/documents/` | PDF 和提取文本路径记在证据包 `documents` 字段；文本只是待核线索。 |
| 市场情绪 | `research/evidence/sentiment/market/YYYY-MM-DD.json` | 内容未变时复用；变化时另存版本。 |
| 个股情绪 | `research/evidence/sentiment/stock/YYYY-MM-DD-CODE.json` | 内容未变时复用；变化时另存版本。 |
| 编辑草稿 | `research/.drafts/YYYY-MM-DD-CODE-简称.md` | 同次内部修复原地更新，不进入正式报告数。 |
| 完整报告 | `research/YYYY-MM-DD-CODE-简称.md` | 显式发布后不可变；真实更新/发布后更正另存版本，原样重试复用。 |
| 补充短记 | `research/supplements/YYYY-MM-DD-CODE-简称-主题.md` | 独立于完整报告序列；已交付补充更正保留其前版及原因。 |
| 筹码快照 | `research/evidence/chips/YYYY-MM-DD-CODE.json` | 按北京时间采集日命名，同日加 `-v2`、`-v3`，实际数据日另存。 |
| 筹码图 | `research/evidence/chips/charts/<SHA256>.svg` | 仅本地分布可生成，按 SVG 内容命名。 |
| 定时任务日志 | `research/evidence/sentiment/schedule.log` | 追加记录运行时间和退出码。 |

证据包的 `schema_version` 目前为 2，情绪快照为 1，独立筹码快照为 1（`kind=chips`）。核心 `collected_at` 为采集开始时间，新包另有 `collection_completed_at`；报价 `retrieved_time` 随实际请求推进，其他观察可能保留适配器批次时间，具体请求时间查看来源 `retrieved_at` 和日志。`period_or_market_time`、`observed_at` 和公告发布时间分别对应数据本身的期间或时点。冻结研究简报时单独写明 `research_as_of`，不把采集开始当作整份研究截止。结构化财务值初始为 `unverified`；PDF 提取段落也须打开原文核对。

常见来源状态：`ok` 为可用结果，`no_record` 为查询完成但无可核记录，`source_failure` 为获取或校验失败，`stale` 为时间不符，`not_supported` 为该来源不覆盖该市场。情绪数据中的 `null` 不等于零；对 `no_record` 还要查看 `detail`，因为部分接口的空返回不能证明真实值为零。

## 可选的 Windows 定时采集

需要每日市场情绪快照时，可由使用者自行安装计划任务。安装脚本会以 `-Force` 注册或替换名为 `stock-research-sentiment-market` 的任务；它要求 Windows 时区为 `China Standard Time`、当前用户已登录，以及绝对的 Python 和工作区路径。

```powershell
$pythonPath = (Get-Command python).Source
$workspaceRoot = (Get-Location).Path
& (Join-Path $stockSkill 'scripts\install_sentiment_schedule.ps1') -PythonPath $pythonPath -WorkspaceRoot $workspaceRoot
```

任务在北京时间 18:00 和 20:00 运行，仅采集国内市场快照；不会自动采集个股、人工帖子或海外参照。采集后会把只读健康检查摘要和 `coverage_exit_code` 追加到同一 `schedule.log`；若采集失败，任务最终退出码仍采用采集失败码。检查任务计划程序的上次结果、日志和当天市场 JSON 的 `issues`。机器关机、解释器失效、日历过期或上游接口异常都可能导致缺日，不能把缺失的历史市场广度伪装成已补录。

## 与当前工作区项目的关系（2026-09-29 对照）

当前工作区 `D:\workspace_study\stock_project` 中还有五个独立项目。它们目前**不是**本 skill 的代码依赖，`stock-research` 也不会自动调用其服务。下表列出值得借鉴或将来按需接入的能力；接入前要核实各项目的实际入口、数据许可、源状态、时间和字段口径。

| 项目 | 已有能力 | 对本 skill 的实际启发 |
| --- | --- | --- |
| `a-stock-data-main` | 自包含取数 skill，提供研报第二来源、行情／公告备援、热榜、事件和行业数据等候选入口。 | 优先借鉴**定向备援**：某一来源失败时才查询独立来源，并保留原始 URL、时间、范围及失败状态；不要把它的整套端点复制进本 skill。 |
| `daily_stock_analysis-main` | `analyze_stock`、批量分析、市场复盘、结构化仪表盘及定时／历史报告。 | 借鉴持续跟踪与报告差异摘要，供同一股票跨日重估；其 AI 结论只能作为另一份分析，不能替代原始披露。 |
| `aiagents-stock-main` | 多分析师研究、数据源降级、持仓监测及类型化决策字段。 | 若需要向其他应用输出结果，定义可选的机器可读摘要；须保留本 skill 的五档评级和“数据不足，暂不评级”，避免直接套用项目的“强烈买入／卖出”口径。 |
| `TradingAgents-AShare-main` | A 股多 Agent 流程、报告历史、定时分析和有认证的 REST API。 | 适合做**可选的外部观点或展示端**。它的单一目标价／止损价不能直接替换本 skill 的情景区间、失效条件和证据门槛。 |
| `TradingAgents-main` | 可配置辩论轮次、决策日志及中断后恢复；A 股使用 `.SS`／`.SZ` 代码。 | 借鉴研究记录、回看和恢复思路。跨项目使用时先统一代码、交易所、研究截止时间和数据来源，不能把多个 Agent 数量当作结论可靠性的证明。 |

当前 `research/` 下的 2026-09-29 三份个股情绪快照（`002409`、`002812`、`600903`）均为 `partial`，共同缺口是东财前 100 热榜和雪球讨论榜 `source_failure`；人工帖子和跨市场参照均为 `not_reviewed`。9 月 22、23、24、28 日市场快照的乐咕广度为 `not_supported`，9 月 29 日才有有效广度。因此近期最具体的改进是：为反复失败的**辅助情绪来源**设计可核对的备援或明确降级，并监测每日市场快照是否完整；不要用其他平台不同口径的数据填成原指标的“补齐值”。这些是对当日已保存文件的观察，不代表上述候选源现在一定可用。

跨项目的最小字段和映射边界已写在 [decision-exchange.md](references/decision-exchange.md)：包括代码与交易所、研究截止时间、报价时间与交易阶段、报告期和股本口径、原始来源链接、验证状态、评级／未评级原因、情景区间及失效事件。其他项目的评分、目标价或 Agent 决策只能作为带来源的**对照观点**，不能升级成已核实的财务事实。实际消费端明确后再设计导出器；本轮没有生成交换 JSON，也没有接入上述项目。

## 维护时优先核对

1. 数据源接口、返回列名和固定依赖版本仍与采集适配器一致；接口成功不代表数字已与原始披露核对。
2. 修改 JSON 字段或状态时，同步更新对应参考文件、报告模板及读取方，保留时间、单位、口径和直接链接。
3. 检查定时任务的工作区、Python 路径和实际产物；单看任务“运行成功”不足以证明快照完整。
4. 保持 `SKILL.md` 为执行规则入口，本文只解释使用和维护，不把 README 当成研究结论或实时行情来源。

## 接口可靠性与人工验收（2026-10-19）

既有证据 schema v1/v2、情绪 schema v1 和版本命名保持可读；新增来源字段全部可选。新状态为 `rate_limited`、`malformed`、`partial`。空响应或字段变更记 malformed／source_failure；只有来源结构有效且能确认完成空查询时才用 no_record。同花顺仍是独立观察，不能修复东财或雪球的失败，也不能升级五日完整性。

运行时对每个 HTTP 请求最多尝试 3 次，默认连接／读取超时 `(5, 15)` 秒，指数退避上限 4 秒加少量抖动。仅网络异常、429、5xx 重试；403 直接冷却，参数／解析错误不重试。普通来源冷却 300 秒，辅助情绪至少 900 秒；按序请求。来源记录包含 attempts、elapsed_ms、HTTP 状态、错误类型、抓取时间、实际覆盖及 request_log。分页可能包含多个各自有重试上限的请求。BaoStock 没有超时 API，放在最长 45 秒的独立 SDK 进程中，失败不会丢失先前采集的报价或日线。

腾讯报价无效／过期时尝试东财；历史日线保持腾讯 → 东财（北交所东财）。失败主源结果与最终来源同时保留，成功备源带 fallback_from。阶段包含盘前（含开盘集合竞价）、连续交易、午休、收盘集合竞价、盘后、非交易日和未知。日历不可用不猜交易日；当日 15:00 前的日线不进入已完成日线。日线在 SDK 排序／去重前检查原始分页，实际检查页数见 coverage；未经过已识别的 HTTP 路线时 raw_pagination_verified 为 false，不能宣称原始分页已核实。价格趋势有争议时仍要独立核对原始行情。

只读查看已有来源历史（不请求网络、不改写 JSON）：

```powershell
python (Join-Path $stockSkill 'scripts\check_source_health.py') --output-dir .
```

`counts`、`record_count`、`failure_record_count` 与 `snapshot_failure_rate` 保留所有不可变快照记录的口径。`event_count`、`failure_event_count`、`failure_rate` 和 `repeated_failure` 按来源与 `run_id` 去重；旧快照依次用 `retrieved_at`／`collected_at` 近似分组，不能称为已确认的独立故障。最近记录和 `latest_failure_diagnostics` 包含错误类型、尝试次数、HTTP 状态、耗时、回退来源及请求摘要；旧字段缺失显示 `null`（不可用）。摘要不输出请求 URL、头、响应正文或原始错误详情。已保存 cooldown_until 是历史记录，不能据此宣称另一个进程仍在冷却。冷却不会跨命令持久化，不应反复重启绕过来源限制。

这份历史摘要不实时验活，失败率还包含过期／覆盖不足；判断故障先看单条原诊断，不能凭失败计数认定根因。实际上游、访问工具、字段／时点及主备条件见 [data-source-policy.md](references/data-source-policy.md) 的数据集表；更换仍访问同一东财端点的SDK不增加独立来源。腾讯日线结构拒绝、东财连接失败、雪球HTTP拒绝、券商EPS过期或待审须分别解释；适配修复／独立备源另列范围，不在本批猜测修复。

工作区允许自动校验时，可检查已发布报告，或在草稿阶段按最终路径预检：

```powershell
python (Join-Path $stockSkill 'scripts\validate_report.py') --report 'research\YYYY-MM-DD-CODE-NAME.md' --workspace .
python (Join-Path $stockSkill 'scripts\create_report.py') --code CODE --name NAME --date YYYY-MM-DD --output-dir . --content-file '已完成草稿.md' --validate
```

校验错误返回1，警告保留为披露项；失败保留可编辑草稿，不生成正式版本。未加`--publish`一律只保存草稿，`--validate`本身也不发布。可用`validate_report.py --report 'research/拟发布文件名.md' --workspace . --content-file 'research/.drafts/实际草稿.md'`按拟发布路径解析链接。若实际工作区规则禁止运行校验，保留待用户验收草稿并提供发布命令；权限依据当前工作区规则，不沿用这份说明中过去某轮执行状态。

报告位于 research/ 时，链接写 `evidence/<精确版本>.json`、`evidence/sentiment/stock/<精确版本>.json` 及前次报告文件名。必填代码、名称、研究日期、资料截止时间、行情时间／阶段、核心和情绪证据的路径／采集时间、最近完整交易日；数据缺失时写明原因。跟踪报告需引用前次报告及新旧核心证据版本，并写“仍有效／需重算／无法判断”。校验器检查结构与引用，不能替代人工阅读原始披露、复算估值或证明财务数字已核实。情绪 partial 是需披露的覆盖警告，不强制否定核心研究。

头部元数据支持 `>`、`-`、`*` 前缀、加粗字段名、字段名空格和中英文冒号，以及分号分隔的已知字段；价格区间同时识别文字范围和`低价≤P＜高价`。真正缺字段、错误路径、无数字价带及未评级报告给出可执行价带仍报错。补充说明另存`supplements/`并关联完整报告，总览主链接保留完整报告；本helper的完整报告校验不用于将短记伪装为完整报告。

## 报告一致性与输入核验

新深研／估值先读 [research-workpaper.md](references/research-workpaper.md)，按采用输入、经营假设、一次计算、决定性敏感性、已采纳最终条件、报告复用的顺序执行。底稿保存在`research/evidence/manual/YYYY-MM-DD-CODE/workpaper.json`，同日工作稿另存`workpaper-v2.json`等；待审方案引用实际审阅版及提议结果ID，正式报告头部链接已采用精确版和`final_decision.id`。字段与更新／继承规则只在该参考中维护，评级定义仍见下列估值／风控规则。它是辅助附件，不能替代核心包；原文核验、计算、裁决及报告对齐仍靠人工，不因文件保存或结构验证成功而视为验收通过。

估值和风控规则以 [valuation-framework.md](references/valuation-framework.md) 与 [position-building-and-risk.md](references/position-building-and-risk.md) 为准。估值输入表区分已核披露、已核券商预测、未核线索和研究者假设；核对财年、实际股本与原文页码，不用利润／加权EPS反推当前股本。券商索引新增 `candidate_for_manual_review`，保留 `usable_for_current_valuation=false`；有当前线索但原文／财年／股本未核时，`broker_forecast_eps` 为 `partial`。旧包的 true 只代表旧的时效筛选，不能直接作为核验结论。

关键派生数字集中计算一次，统一单位和显示精度；安全边际为 `1－现价／模型价值`，至模型价值的涨跌空间为 `模型价值／现价－1`。核心结论中的最终价带和激活条件是同一报告的唯一口径；“确认仓／证据先兑现”超出旧区间时先重估并公布新上限，不能直接放宽入口。用户未提供配置及风险预算时，不预设试仓或最大仓位比例。跟踪报告解释输入、证据及其估值／行动影响，未变的模型无需为了更新而改变。

报告头部分别写 Agent 流程、重大证据缺口和验收状态。完整回应可包含 unresolved／evidence_missing，流程完成不代表证据已充分；必要风险证据未核时仍只观察。已知证据文件或合同错误保留草稿，自动验证受工作区限制时写“待用户验收”。校验器结果新增 `verification_scope=structure_and_local_references_only`，有效辅助清单列入 `auxiliary_paths`，不冒充核心证据；成功不证明财务事实、估值算术或所有文字行动条件正确。历史报告和快照不随规则升级改写。

新快照记录 `runtime_version`、`run_id`；新写入的来源必须有 HTTP(S) URL 或 `adapter:<name>` 标识，行情阶段必须使用规范值。旧快照只读兼容，`continuous`／`post_close` 分别解释为 `intraday`／`postmarket`，无法区分开盘或收盘的 `auction` 保持 unknown 并提示人工确认。`coverage.calendar_status` 区分 `verified`、`failed`、`not_requested`，配合 `calendar_verified` 判断；日历不可用时历史行情为 partial，有效日期留空，报价数据仍保留。

情绪日历失败会保存 `collection_status=failed`、`as_of_trade_date=null`、`calendar_unavailable` 和运行诊断，路径为 `research/evidence/sentiment/diagnostics/stock/采集日期-代码[-vN].json` 或 `diagnostics/market/采集日期[-vN].json`，退出码为 2。这些文件不进入正常交易日／五日覆盖读取，也不能充当报告已完成的证据；普通已确认空查询仍使用 no_record。常规 HTTP 响应在完整缓冲后关闭；流式 PDF 由下载方读取完毕后关闭，AKShare 流式响应在适配器返回时关闭。多级 partial 选择有效观测项更多的结果，并标记 `selected_for_payload`、保留全部来源结果与回退链。

| 情况 | 处理 |
|---|---|
| 403／429、连接重置、超时 | 先读诊断包和来源健康汇总；等冷却或走已定义备源，不反复请求。 |
| HTTP 200 但空对象／空表、字段变化 | 查 error_type、request_log 与字段契约；不解释成没有记录，修复解析或人工核验。 |
| 返回代码或市场前缀不符 | 拒绝结果，核对六位代码、交易所与来源代码；不沿用错股价格。 |
| 交易日历错误／报价过期 | 保留 unknown／stale；核对官方交易日和供应商交易时间，不按周一至周五补猜。 |
| 午休、收盘竞价、盘后、非交易日 | 明确阶段和实际报价日期；不把抓取时间当作最新成交或完整日线。 |
| 巨潮索引／PDF 失败 | 走巨潮或对应交易所官方入口人工核验，不以第三方新闻替代。 |
| 研报失败或没有当前 EPS | 新浪列表／同花顺聚合页只作线索；核对原文、财年、发布日期、事件后口径前，不写为可用预测。 |
| 报告断链／证据版本不一致 | 保留草稿；逐份定位正确版本，先备份再单独修复，不自动改写旧报告或 JSON。 |

本轮已接入日志／严格解析、报价与日线备源／冷却，以及可选报告校验入口。历史报告批量扫描与修复、真实单股／情绪采集验收、定时任务下一次运行日志和用户验收结果仍由用户确认；没有改变既有研究结论。测试文件按要求未修改，其中针对旧全局网络补丁和旧阶段字段的断言仍需使用者按新契约审阅。
