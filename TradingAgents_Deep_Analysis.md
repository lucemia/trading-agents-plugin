# TradingAgents Deep Analysis: Pipeline, Prompts & Process

> Source: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)  
> Analysis Date: 2026-05-02

---

## Table of Contents

1. [Pipeline Flow & LangGraph Architecture](#1-pipeline-flow--langgraph-architecture)
2. [Agent Prompts (Full Text)](#2-agent-prompts-full-text)
3. [State Management](#3-state-management)
4. [Debate Mechanics](#4-debate-mechanics)
5. [Tool Implementations](#5-tool-implementations)
6. [Memory System](#6-memory-system)
7. [Structured Output System](#7-structured-output-system)
8. [LLM Client Factory](#8-llm-client-factory)

---

## 1. Pipeline Flow & LangGraph Architecture

### Graph Structure

The system uses a `StateGraph`-based LangGraph pipeline. All agent logic lives in `tradingagents/graph/setup.py` and `trading_graph.py`.

```
START
  │
  ▼
[Market Analyst] ──► [tools_market] ──► [Msg Clear Market]
  │
  ▼
[Social Media Analyst] ──► [tools_social] ──► [Msg Clear Social]
  │
  ▼
[News Analyst] ──► [tools_news] ──► [Msg Clear News]
  │
  ▼
[Fundamentals Analyst] ──► [tools_fundamentals] ──► [Msg Clear Fundamentals]
  │
  ▼
[Bull Researcher] ◄──────────────────────────────────────┐
  │                                                       │
  ▼                                                       │
[Bear Researcher] ─────────────────────────── (debate rounds)
  │  (when count >= 2 × max_debate_rounds)
  ▼
[Research Manager]
  │
  ▼
[Trader]
  │
  ▼
[Aggressive Analyst] ◄──────────────────────────────────────┐
  │                                                          │
  ▼                                                          │
[Conservative Analyst] ──────────────────────── (risk rounds)
  │
  ▼
[Neutral Analyst]
  │  (when count >= 3 × max_risk_discuss_rounds)
  ▼
[Portfolio Manager]
  │
  ▼
END
```

### Edge Configuration (`setup.py` lines 110–180)

```python
# START → first selected analyst
workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

# Each analyst: conditional tool-call loop
workflow.add_conditional_edges(
    current_analyst,
    conditional_logic.should_continue_{analyst_type},
    [current_tools, current_clear]
)
workflow.add_edge(current_tools, current_analyst)    # Tool result loops back
workflow.add_edge(current_clear, next_analyst)        # Clear → advance

# Bull/Bear bidirectional loop
workflow.add_conditional_edges(
    "Bull Researcher",
    conditional_logic.should_continue_debate,
    {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"}
)
workflow.add_conditional_edges(
    "Bear Researcher",
    conditional_logic.should_continue_debate,
    {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"}
)

# Research Manager → Trader (always)
workflow.add_edge("Research Manager", "Trader")

# 3-way risk debate rotation
workflow.add_conditional_edges(
    "Aggressive Analyst",
    conditional_logic.should_continue_risk_analysis,
    {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"}
)
workflow.add_conditional_edges(
    "Conservative Analyst",
    conditional_logic.should_continue_risk_analysis,
    {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"}
)
workflow.add_conditional_edges(
    "Neutral Analyst",
    conditional_logic.should_continue_risk_analysis,
    {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"}
)

workflow.add_edge("Portfolio Manager", END)
```

### Conditional Logic (`conditional_logic.py`)

**Analyst tool-call routing** — each analyst follows a tool loop until no more tool calls:
```python
def should_continue_market(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools_market"
    return "Msg Clear Market"
```

**Investment Debate Loop** (lines 46–55):
```python
def should_continue_debate(state: AgentState) -> str:
    count = state["investment_debate_state"]["count"]
    if count >= 2 * self.max_debate_rounds:
        return "Research Manager"   # Default: stop after Bull+Bear speak once
    if state["investment_debate_state"]["current_response"].startswith("Bull"):
        return "Bear Researcher"    # Bull just spoke → Bear's turn
    return "Bull Researcher"        # Bear just spoke (or start) → Bull's turn
```

**Risk Analysis Loop** (lines 57–67):
```python
def should_continue_risk_analysis(state: AgentState) -> str:
    count = state["risk_debate_state"]["count"]
    if count >= 3 * self.max_risk_discuss_rounds:
        return "Portfolio Manager"  # Default: stop after Agg+Cons+Neut speak once
    if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
        return "Conservative Analyst"
    if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
        return "Neutral Analyst"
    return "Aggressive Analyst"     # Start with Aggressive or resume after Neutral
```

---

## 2. Agent Prompts (Full Text)

### Shared Wrapper (all tool-using analysts)

All analysts that use tools receive this wrapper as their human message prefix:

```
You are a helpful AI assistant, collaborating with other assistants. Use the
provided tools to progress towards answering the question. If you are unable to
fully answer, that's OK; another assistant with different tools will help where
you left off. Execute what you can to make progress. If you or any other assistant
has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable, prefix your
response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to
stop. You have access to the following tools: {tool_names}.{system_message}
For your reference, the current date is {current_date}. {instrument_context}
```

---

### Market Analyst (`agents/analysts/market_analyst.py` lines 22–50)

**System Message:**
```
You are a trading assistant tasked with analyzing financial markets. Your role is
to select the **most relevant indicators** for a given market condition or trading
strategy from the following list. The goal is to choose up to **8 indicators** that
provide complementary insights without redundancy. Categories and each category's
indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend
  direction and serve as dynamic support/resistance. Tips: It lags price; combine
  with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall
  market trend and identify golden/death cross setups. Tips: It reacts slowly; best
  for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts
  in momentum and potential entry points. Tips: Prone to noise in choppy markets; use
  alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers
  and divergence as signals of trend changes. Tips: Confirm with other indicators in
  low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with
  the MACD line to trigger trades. Tips: Should be part of a broader strategy to
  avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage:
  Visualize momentum strength and spot divergence early. Tips: Can be volatile;
  complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply
  70/30 thresholds and watch for divergence to signal reversals. Tips: In strong
  trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage:
  Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and
  lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle
  line. Usage: Signals potential overbought conditions and breakout zones. Tips:
  Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle
  line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis
  to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels
  and adjust position sizes based on current market volatility. Tips: It's a reactive
  measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by
  integrating price action with volume data. Tips: Watch for skewed results from
  volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid
  redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why
  they are suitable for the given market context. When you tool call, please use the
  exact name of the indicators provided above as they are defined parameters,
  otherwise your call will fail. Please make sure to call get_stock_data first to
  retrieve the CSV that is needed to generate indicators. Then use get_indicators
  with the specific indicator names. Write a very detailed and nuanced report of the
  trends you observe. Provide specific, actionable insights with supporting evidence
  to help traders make informed decisions. Make sure to append a Markdown table at
  the end of the report to organize key points in the report, organized and easy to
  read. [language instruction if configured]
```

**Tools available:** `get_stock_data`, `get_indicators`

---

### Social Media Analyst (`agents/analysts/social_media_analyst.py` lines 15–19)

**System Message:**
```
You are a social media and company specific news researcher/analyst tasked with
analyzing social media posts, recent company news, and public sentiment for a
specific company over the past week. You will be given a company's name your
objective is to write a comprehensive long report detailing your analysis, insights,
and implications for traders and investors on this company's current state after
looking at social media and what people are saying about that company, analyzing
sentiment data of what people feel each day about the company, and looking at recent
company news. Use the get_news(query, start_date, end_date) tool to search for
company-specific news and social media discussions. Try to look at all sources
possible from social media to sentiment to news. Provide specific, actionable
insights with supporting evidence to help traders make informed decisions. Make sure
to append a Markdown table at the end of the report to organize key points in the
report, organized and easy to read. [language instruction if configured]
```

**Tools available:** `get_news`

---

### News Analyst (`agents/analysts/news_analyst.py` lines 21–25)

**System Message:**
```
You are a news researcher tasked with analyzing recent news and trends over the past
week. Please write a comprehensive report of the current state of the world that is
relevant for trading and macroeconomics. Use the available tools:
get_news(query, start_date, end_date) for company-specific or targeted news searches,
and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news.
Provide specific, actionable insights with supporting evidence to help traders make
informed decisions. Make sure to append a Markdown table at the end of the report to
organize key points in the report, organized and easy to read. [language instruction
if configured]
```

**Tools available:** `get_news`, `get_global_news`, `get_insider_transactions`

---

### Fundamentals Analyst (`agents/analysts/fundamentals_analyst.py` lines 26–31)

**System Message:**
```
You are a researcher tasked with analyzing fundamental information over the past
week about a company. Please write a comprehensive report of the company's
fundamental information such as financial documents, company profile, basic company
financials, and company financial history to gain a full view of the company's
fundamental information to inform traders. Make sure to include as much detail as
possible. Provide specific, actionable insights with supporting evidence to help
traders make informed decisions. Make sure to append a Markdown table at the end of
the report to organize key points in the report, organized and easy to read. Use the
available tools: `get_fundamentals` for comprehensive company analysis,
`get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific
financial statements. [language instruction if configured]
```

**Tools available:** `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`

---

### Bull Researcher (`agents/researchers/bull_researcher.py` lines 15–32)

**Prompt Template (all variables injected at runtime):**
```
You are a Bull Analyst advocating for investing in the stock. Your task is to build
a strong, evidence-based case emphasizing growth potential, competitive advantages,
and positive market indicators. Leverage the provided research and data to address
concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue
  projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding,
  or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive
  news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and
  sound reasoning, addressing concerns thoroughly and showing why the bull
  perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly
  with the bear analyst's points and debating effectively rather than just listing
  data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's
concerns, and engage in a dynamic debate that demonstrates the strengths of the
bull position.
```

---

### Bear Researcher (`agents/researchers/bear_researcher.py` lines 15–34)

**Prompt Template:**
```
You are a Bear Analyst making the case against investing in the stock. Your goal is
to present a well-reasoned argument emphasizing risks, challenges, and negative
indicators. Leverage the provided research and data to highlight potential downsides
and counter bullish arguments effectively.

Key points to focus on:
- Risks and Challenges: Highlight factors like market saturation, financial
  instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market
  positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent
  adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and
  sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging
  with the bull analyst's points and debating effectively rather than simply listing
  facts.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims,
and engage in a dynamic debate that demonstrates the risks and weaknesses of
investing in the stock.
```

---

### Research Manager (`agents/managers/research_manager.py` lines 22–40)

**Prompt Template:**
```
As the Research Manager and debate facilitator, your role is to critically evaluate
this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the
  position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the
  position

Commit to a clear stance whenever the debate's strongest arguments warrant one;
reserve Hold for situations where the evidence on both sides is genuinely balanced.

---

**Debate History:**
{history}
```

**Output Schema:** `ResearchPlan` (Pydantic)
```python
class ResearchPlan(BaseModel):
    recommendation: PortfolioRating   # Buy | Overweight | Hold | Underweight | Sell
    rationale: str                    # Key points from debate
    strategic_actions: str            # Concrete trader instructions
```

**Rendered Markdown Output:**
```markdown
**Recommendation**: Buy

**Rationale**: The bull case emphasized consistent revenue growth...

**Strategic Actions**: Initiate long position on weakness to $148 support...
```

---

### Trader (`agents/trader.py` lines 25–45)

**System Message:**
```
You are a trading agent analyzing market data to make investment decisions. Based on
your analysis, provide a specific recommendation to buy, sell, or hold. Anchor your
reasoning in the analysts' reports and the research plan.
```

**User Message:**
```
Based on a comprehensive analysis by a team of analysts, here is an investment plan
tailored for {company_name}. {instrument_context} This plan incorporates insights
from current technical market trends, macroeconomic indicators, and social media
sentiment. Use this plan as a foundation for evaluating your next trading decision.

Proposed Investment Plan: {investment_plan}

Leverage these insights to make an informed and strategic decision.
```

**Output Schema:** `TraderProposal` (Pydantic)
```python
class TraderProposal(BaseModel):
    action: TraderAction              # Buy | Hold | Sell
    reasoning: str                    # 2-4 sentences anchored in reports
    entry_price: Optional[float]
    stop_loss: Optional[float]
    position_sizing: Optional[str]    # e.g., "5% of portfolio"
```

**Rendered Markdown Output** (note: always ends with the sentinel line):
```markdown
**Action**: Buy

**Reasoning**: Technical setup confirmed breakout above key resistance...

**Entry Price**: 150.25

**Stop Loss**: 145.00

**Position Sizing**: 5% of portfolio

FINAL TRANSACTION PROPOSAL: **BUY**
```

---

### Aggressive Risk Analyst (`agents/risk/aggressive_debator.py` lines 19–31)

**Prompt Template:**
```
As the Aggressive Risk Analyst, your role is to actively champion high-reward,
high-risk opportunities, emphasizing bold strategies and competitive advantages.
When evaluating the trader's decision or plan, focus intently on the potential
upside, growth potential, and innovative benefits—even when these come with elevated
risk. Use the provided market data and sentiment analysis to strengthen your
arguments and challenge the opposing views. Specifically, respond directly to each
point made by the conservative and neutral analysts, countering with data-driven
rebuttals and persuasive reasoning. Highlight where their caution might miss
critical opportunities or where their assumptions may be overly conservative. Here
is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning
and critiquing the conservative and neutral stances to demonstrate why your
high-reward perspective offers the best path forward. Incorporate insights from the
following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments
from the conservative analyst: {current_conservative_response} Here are the last
arguments from the neutral analyst: {current_neutral_response}. If there are no
responses from the other viewpoints yet, present your own argument based on the
available data.

Engage actively by addressing any specific concerns raised, refuting the weaknesses
in their logic, and asserting the benefits of risk-taking to outpace market norms.
Maintain a focus on debating and persuading, not just presenting data. Challenge
each counterpoint to underscore why a high-risk approach is optimal. Output
conversationally as if you are speaking without any special formatting.
```

---

### Conservative Risk Analyst (`agents/risk/conservative_debator.py` lines 19–31)

**Prompt Template:**
```
As the Conservative Risk Analyst, your primary objective is to protect assets,
minimize volatility, and ensure steady, reliable growth. You prioritize stability,
security, and risk mitigation, carefully assessing potential losses, economic
downturns, and market volatility. When evaluating the trader's decision or plan,
critically examine high-risk elements, pointing out where the decision may expose
the firm to undue risk and where more cautious alternatives could secure
long-term gains. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral
Analysts, highlighting where their views may overlook potential threats or fail to
prioritize sustainability. Respond directly to their points, drawing from the
following data sources to build a convincing case for a low-risk approach adjustment
to the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from
the aggressive analyst: {current_aggressive_response} Here is the last response from
the neutral analyst: {current_neutral_response}. If there are no responses from the
other viewpoints yet, present your own argument based on the available data.

Engage by questioning their optimism and emphasizing the potential downsides they
may have overlooked. Address each of their counterpoints to showcase why a
conservative stance is ultimately the safest path for the firm's assets. Focus on
debating and critiquing their arguments to demonstrate the strength of a low-risk
strategy over their approaches. Output conversationally as if you are speaking
without any special formatting.
```

---

### Neutral Risk Analyst (`agents/risk/neutral_debator.py` lines 19–31)

**Prompt Template:**
```
As the Neutral Risk Analyst, your role is to provide a balanced perspective,
weighing both the potential benefits and risks of the trader's decision or plan. You
prioritize a well-rounded approach, evaluating the upsides and downsides while
factoring in broader market trends, potential economic shifts, and diversification
strategies. Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing
out where each perspective may be overly optimistic or overly cautious. Use insights
from the following data sources to support a moderate, sustainable strategy to
adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from
the aggressive analyst: {current_aggressive_response} Here is the last response from
the conservative analyst: {current_conservative_response}. If there are no responses
from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically, addressing weaknesses in the
aggressive and conservative arguments to advocate for a more balanced approach.
Challenge each of their points to illustrate why a moderate risk strategy might
offer the best of both worlds, providing growth potential while safeguarding against
extreme volatility. Focus on debating rather than simply presenting data, aiming to
show that a balanced view can lead to the most reliable outcomes. Output
conversationally as if you are speaking without any special formatting.
```

---

### Portfolio Manager (`agents/managers/portfolio_manager.py` lines 42–64)

**Prompt Template:**
```
As the Portfolio Manager, synthesize the risk analysts' debate and deliver the
final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.
{language_instruction}
```

**Memory Injection** — `{lessons_line}` expands to past context when available:
```
- Lessons from prior decisions and outcomes:
Past analyses of AAPL (most recent first):
[2025-01-15 | AAPL | Buy | +3.2% | +1.5% | 5d]

DECISION:
**Rating**: Buy
...

REFLECTION:
Call was directional correct with +1.5% alpha. The bull thesis on margin expansion held...

Recent cross-ticker lessons:
[2025-01-14 | TSLA | Sell | -2.1%]
Regulatory headwinds proved more significant than expected...
```

**Output Schema:** `PortfolioDecision` (Pydantic)
```python
class PortfolioDecision(BaseModel):
    rating: PortfolioRating           # Buy | Overweight | Hold | Underweight | Sell
    executive_summary: str            # 2-4 sentences on action plan
    investment_thesis: str            # Detailed reasoning with evidence
    price_target: Optional[float]
    time_horizon: Optional[str]       # e.g., "3-6 months"
```

---

## 3. State Management

### `AgentState` Definition (`graph/agent_states.py`)

```python
class AgentState(MessagesState):
    # Instrument identification
    company_of_interest: str           # Ticker symbol
    trade_date: str                    # "YYYY-MM-DD"
    sender: str                        # Agent name (for routing)

    # Analyst outputs (accumulated, never cleared after use)
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str

    # Investment debate phase
    investment_debate_state: InvestDebateState
    investment_plan: str               # Research Manager's plan
    trader_investment_plan: str        # Trader's proposal

    # Risk debate phase
    risk_debate_state: RiskDebateState
    final_trade_decision: str          # Portfolio Manager's final decision

    # Memory injection
    past_context: str                  # Lessons from prior runs (read-only)
```

### `InvestDebateState` (Investment Debate Tracking)

```python
class InvestDebateState(TypedDict):
    bull_history: str       # All Bull messages concatenated
    bear_history: str       # All Bear messages concatenated
    history: str            # Combined debate history
    current_response: str   # Last message (starts with "Bull Analyst:" or "Bear Analyst:")
    judge_decision: str     # Research Manager's output
    count: int              # Total debate turns (incremented on each Bull/Bear message)
```

**Message wrapping pattern:**
```python
argument = f"Bull Analyst: {response.content}"
new_state = {
    "history": history + "\n" + argument,
    "bull_history": bull_history + "\n" + argument,
    "current_response": argument,   # Used by conditional_logic to determine next speaker
    "count": count + 1,
}
```

### `RiskDebateState` (Risk Debate Tracking)

```python
class RiskDebateState(TypedDict):
    aggressive_history: str
    conservative_history: str
    neutral_history: str
    history: str                       # Combined all-three history
    latest_speaker: str                # "Aggressive" | "Conservative" | "Neutral"
    current_aggressive_response: str
    current_conservative_response: str
    current_neutral_response: str
    judge_decision: str
    count: int
```

**Message wrapping pattern:**
```python
argument = f"Aggressive Analyst: {response.content}"
new_state = {
    "history": history + "\n" + argument,
    "aggressive_history": aggressive_history + "\n" + argument,
    "latest_speaker": "Aggressive",      # Used by conditional_logic for rotation
    "current_aggressive_response": argument,
    "count": count + 1,
}
```

### State Flow Summary

| Phase | State Fields Written | State Fields Read |
|-------|----------------------|-------------------|
| Analyst Chain | `market_report`, `sentiment_report`, `news_report`, `fundamentals_report` | `company_of_interest`, `trade_date` |
| Msg Clear | `messages` (remove + add placeholder) | — |
| Bull/Bear Debate | `investment_debate_state.*` | All 4 analyst reports, `investment_debate_state` |
| Research Manager | `investment_plan` | `investment_debate_state.history` |
| Trader | `trader_investment_plan` | `investment_plan` |
| Risk Debate | `risk_debate_state.*` | All 4 reports, `trader_investment_plan`, `risk_debate_state` |
| Portfolio Manager | `final_trade_decision` | `risk_debate_state.*`, `investment_plan`, `trader_investment_plan`, `past_context` |

---

## 4. Debate Mechanics

### Investment Debate (Bull vs Bear)

**Flow with `max_debate_rounds=1` (default):**

```
count=0: Bull speaks → count=1, current_response="Bull Analyst: ..."
  conditional: "Bull" prefix → Bear's turn

count=1: Bear speaks → count=2, current_response="Bear Analyst: ..."
  conditional: count(2) >= 2*1 → Research Manager
```

**Flow with `max_debate_rounds=2`:**

```
count=0 → Bull (count=1) → Bear (count=2) → Bull (count=3) → Bear (count=4)
  conditional: count(4) >= 2*2 → Research Manager
```

**Data each debater receives:**
- All 4 analyst reports (market, sentiment, news, fundamentals) — full text
- `history` — full transcript of all prior debate turns
- `current_response` — the opposing side's most recent argument

**Key design decision:** Debaters receive the *full transcript* (`history`) plus only the *last opposing message* (`current_response`). This forces explicit engagement with the most recent counterpoint while having full context.

---

### Risk Management Debate (3-Way Rotation)

**Flow with `max_risk_discuss_rounds=1` (default):**

```
count=0: Aggressive speaks → latest_speaker="Aggressive", count=1
  conditional: "Aggressive" → Conservative's turn

count=1: Conservative speaks → latest_speaker="Conservative", count=2
  conditional: "Conservative" → Neutral's turn

count=2: Neutral speaks → latest_speaker="Neutral", count=3
  conditional: count(3) >= 3*1 → Portfolio Manager
```

**Data each risk analyst receives:**
- All 4 analyst reports
- `trader_decision` — the Trader's proposed action
- `history` — full 3-way debate transcript
- The *other two* analysts' most recent responses (`current_*_response`)

**Key design decision:** Each risk analyst sees what the *other two* said last, enabling targeted rebuttals. The Aggressive analyst sees Conservative + Neutral responses; Conservative sees Aggressive + Neutral; Neutral sees both.

---

## 5. Tool Implementations

### Tool Registry (`trading_graph.py` lines 154–188)

```python
self.tool_nodes = {
    "market": ToolNode([get_stock_data, get_indicators]),
    "social": ToolNode([get_news]),
    "news":   ToolNode([get_news, get_global_news, get_insider_transactions]),
    "fundamentals": ToolNode([
        get_fundamentals, get_balance_sheet,
        get_cashflow, get_income_statement
    ]),
}
```

### Tool Signatures

All tools are `@tool`-decorated LangChain functions. They delegate via `route_to_vendor()`.

```python
# Core stock data
@tool
def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve OHLCV historical price data."""
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)

# Technical indicators
@tool
def get_indicators(
    symbol: str,
    indicator: str,        # Exact name from the indicator list
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Retrieve a single technical indicator with analysis."""
    return route_to_vendor("get_indicators", symbol, indicator, curr_date, look_back_days)

# Fundamental data
@tool
def get_fundamentals(ticker: str, curr_date: str) -> str: ...
@tool
def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str: ...
@tool
def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str: ...
@tool
def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str: ...

# News and events
@tool
def get_news(ticker: str, start_date: str, end_date: str) -> str: ...
@tool
def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 5) -> str: ...
@tool
def get_insider_transactions(ticker: str) -> str: ...
```

### Supported Technical Indicators

| Category | Indicator Name | Description |
|----------|---------------|-------------|
| Moving Averages | `close_50_sma` | 50-period SMA |
| Moving Averages | `close_200_sma` | 200-period SMA |
| Moving Averages | `close_10_ema` | 10-period EMA |
| MACD | `macd` | MACD line |
| MACD | `macds` | MACD Signal |
| MACD | `macdh` | MACD Histogram |
| Momentum | `rsi` | RSI (14) |
| Bollinger | `boll` | Bollinger Middle (20 SMA) |
| Bollinger | `boll_ub` | Bollinger Upper Band |
| Bollinger | `boll_lb` | Bollinger Lower Band |
| Volatility | `atr` | Average True Range |
| Volume | `vwma` | Volume-Weighted Moving Average |

### Vendor Routing (`dataflows/interface.py`)

```python
def route_to_vendor(tool_name: str, *args, **kwargs) -> str:
    vendor = config["tool_vendors"].get(tool_name) \
          or config["data_vendors"].get(tool_category(tool_name))
    
    if vendor == "yfinance":
        return yfinance_module.tool_name(*args, **kwargs)
    elif vendor == "alpha_vantage":
        return alpha_vantage_module.tool_name(*args, **kwargs)
```

**Tool return format:** All tools return **formatted strings** (markdown tables + prose narratives), not raw JSON. This is intentional — data flows as readable text for LLM consumption.

---

## 6. Memory System

### Architecture Overview

The memory system uses an **append-only markdown file** at `~/.tradingagents/memory/trading_memory.md`. It operates in two phases:

- **Phase A (store):** Called immediately after analysis — saves the decision as `pending`
- **Phase B (resolve):** Called at start of *next* analysis for same ticker — fetches price return, generates reflection, updates log

### Log Format

```markdown
[2025-01-15 | AAPL | Buy | +3.2% | +1.5% | 5d]

DECISION:
**Rating**: Buy
**Executive Summary**: Entry on strength; conservative sizing recommended.
**Investment Thesis**: Technical breakout confirmed by volume...

REFLECTION:
The directional call was correct with +1.5% alpha vs SPY. The bull thesis on margin
expansion held as expected, but the initial timing was slightly early. Next similar
setup: wait for a retest of the breakout level before entering.

<!-- ENTRY_END -->

[2025-01-16 | AAPL | Hold | pending]

DECISION:
**Rating**: Hold
**Executive Summary**: Consolidation phase expected...

<!-- ENTRY_END -->
```

**Tag format:** `[trade_date | ticker | rating | raw_return | alpha_return | holding_days]`  
**Pending entries:** `[trade_date | ticker | rating | pending]`  
**Delimiter:** `<!-- ENTRY_END -->` — an HTML comment that LLMs cannot reproduce accidentally

### Phase A: Decision Capture (`memory.py: store_decision`)

```python
def store_decision(ticker: str, trade_date: str, final_trade_decision: str) -> None:
    rating = parse_rating(final_trade_decision)  # Extract rating from text
    tag = f"[{trade_date} | {ticker} | {rating} | pending]"

    # Idempotency guard: skip if already logged
    if tag_exists_in_file(tag):
        return

    entry = f"{tag}\n\nDECISION:\n{final_trade_decision}{SEPARATOR}"
    append_to_file(entry)
```

### Phase B: Outcome Resolution (`memory.py: _resolve_pending_entries`)

```python
def _resolve_pending_entries(self, ticker: str) -> None:
    pending = [e for e in self.get_pending_entries() if e["ticker"] == ticker]
    updates = []

    for entry in pending:
        # Fetch price return over 5-day holding period
        raw, alpha, days = self._fetch_returns(ticker, entry["date"])
        if raw is None:
            continue  # Price data not yet available (too recent)

        # Generate reflection using quick_think_llm
        reflection = self.reflector.reflect_on_final_decision(
            final_decision=entry.get("decision", ""),
            raw_return=raw,
            alpha_return=alpha,
        )
        updates.append({...})

    if updates:
        self.memory_log.batch_update_with_outcomes(updates)  # Atomic batch write
```

### Reflection Prompt (`agents/utils/reflection.py` lines 14–29)

```
You are a trading analyst reviewing your own past decision now that the outcome is known.
Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).

Cover in order:
1. Was the directional call correct? (cite the alpha figure)
2. Which part of the investment thesis held or failed?
3. One concrete lesson to apply to the next similar analysis.

Be specific and terse. Your output will be stored verbatim in a decision log
and re-read by future analysts, so every word must earn its place.
```

**Input to reflection LLM:**
```
Raw return: +3.2%
Alpha vs SPY: +1.5%

Final Decision:
**Rating**: Buy
**Executive Summary**: Entry on strength...
[full decision text]
```

### Phase C: Context Injection (`memory.py: get_past_context`)

```python
def get_past_context(self, ticker: str, n_same=5, n_cross=3) -> str:
    same_ticker = [e for e in entries if e["ticker"] == ticker][-5:]
    cross_ticker = [e for e in entries if e["ticker"] != ticker][-3:]

    output = f"Past analyses of {ticker} (most recent first):\n"
    output += format_full_entries(same_ticker)
    output += "\n\nRecent cross-ticker lessons:\n"
    output += format_reflection_only(cross_ticker)  # Only tag + reflection, no full decision
    return output
```

**Injected into Portfolio Manager prompt as `{lessons_line}`:**
```
- Lessons from prior decisions and outcomes:
Past analyses of AAPL (most recent first):
[2025-01-15 | AAPL | Buy | +3.2% | +1.5% | 5d]

DECISION: ...
REFLECTION: The directional call was correct...

Recent cross-ticker lessons:
[2025-01-14 | TSLA | Sell | -2.1%]
Regulatory headwinds proved more significant than expected...
```

### Optional Log Rotation

```python
def _apply_rotation(self, blocks: List[str]) -> List[str]:
    """Drop oldest resolved entries when count exceeds max_entries config."""
    resolved_count = sum(1 for block in blocks if is_resolved(block))
    if resolved_count > self._max_entries:
        drop = resolved_count - self._max_entries
        # Drop oldest resolved, preserve all pending entries
```

---

## 7. Structured Output System

### Design: Graceful Fallback

Three agents produce structured output: Research Manager, Trader, Portfolio Manager.
The system attempts provider-native structured output, then falls back to free text.

```python
# structured.py

def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return llm.with_structured_output(schema) or None if unsupported."""
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError):
        logger.warning(f"{agent_name}: falling back to free-text generation")
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)      # Pydantic → markdown string
        except Exception:
            logger.warning(f"{agent_name}: structured failed, retrying as free text")

    # Free-text fallback
    response = plain_llm.invoke(prompt)
    return response.content
```

### Provider-Specific Structured Output

| Provider | Method | Notes |
|----------|--------|-------|
| OpenAI | `function_calling` | Forced (avoids Pydantic warnings from Responses API's union-typed parsed response) |
| Anthropic | Tool use (native) | `with_structured_output` via LangChain → forced tool call |
| Google Gemini | `response_schema` | Gemini 3 response schema mode |
| Others | Free-text fallback | If `with_structured_output` raises `NotImplementedError` |

### Pydantic Schemas (`agents/utils/schemas.py`)

```python
class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"

class TraderAction(str, Enum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"

class ResearchPlan(BaseModel):
    recommendation: PortfolioRating
    rationale: str
    strategic_actions: str

class TraderProposal(BaseModel):
    action: TraderAction
    reasoning: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    position_sizing: Optional[str] = None

class PortfolioDecision(BaseModel):
    rating: PortfolioRating
    executive_summary: str
    investment_thesis: str
    price_target: Optional[float] = None
    time_horizon: Optional[str] = None
```

### Content Normalization (`base_client.py: normalize_content`)

Some providers (OpenAI Responses API, Gemini 3) return multi-block responses:
```python
# Raw provider response:
content = [
    {"type": "reasoning", "text": "...thinking..."},
    {"type": "text", "text": "...actual output..."}
]

# After normalize_content():
content = "...actual output..."   # Only text blocks, reasoning discarded
```

This normalization runs at the client level, transparent to all agents.

---

## 8. LLM Client Factory

### Factory Pattern (`llm_clients/factory.py`)

```python
_OPENAI_COMPATIBLE = ("openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter")

def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    if provider.lower() in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider.lower(), **kwargs)

    if provider.lower() == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider.lower() == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider.lower() == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported provider: {provider}")
```

### OpenAI Client (`llm_clients/openai_client.py`)

```python
_PROVIDER_CONFIG = {
    "xai":        ("https://api.x.ai/v1",           "XAI_API_KEY"),
    "deepseek":   ("https://api.deepseek.com",       "DEEPSEEK_API_KEY"),
    "qwen":       ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm":        ("https://api.z.ai/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",  "OPENROUTER_API_KEY"),
    "ollama":     ("http://localhost:11434/v1",      None),
}
```

- Native OpenAI: uses `use_responses_api=True`
- Third-party: standard Chat Completions API at provider-specific base URL
- Structured output: defaults to `method="function_calling"` to avoid Pydantic warnings

### Anthropic Client (`llm_clients/anthropic_client.py`)

**Passthrough kwargs:** `timeout`, `max_retries`, `api_key`, `max_tokens`, `callbacks`, `http_client`, `http_async_client`, `effort`

- `effort`: Extended thinking effort level — "low" | "medium" | "high"
- Wraps `ChatAnthropic` in `NormalizedChatAnthropic` for content block normalization

### Google Client (`llm_clients/google_client.py`)

**Thinking Level Mapping:**

| Config Value | Gemini 3 Pro | Gemini 3 Flash | Gemini 2.5 |
|--------------|-------------|----------------|------------|
| `"minimal"` | `"low"` (remapped) | `"minimal"` | `thinking_budget=0` |
| `"low"` | `"low"` | `"low"` | `thinking_budget=0` |
| `"high"` | `"high"` | `"high"` | `thinking_budget=-1` (dynamic) |

### LLM Assignment in `TradingAgentsGraph`

```python
# Two distinct LLMs with different models/capabilities
self.deep_thinking_llm = deep_client.get_llm()   # For: Research Manager, Portfolio Manager
self.quick_thinking_llm = quick_client.get_llm() # For: All analysts, Trader, Risk analysts

# Both share the same provider + thinking config
# Default config:
#   deep_think_llm: "claude-opus-4-6"
#   quick_think_llm: "claude-sonnet-4-6"
```

### Provider-Specific Thinking Config (`_get_provider_kwargs`)

```python
def _get_provider_kwargs(self) -> Dict[str, Any]:
    provider = self.config.get("llm_provider", "").lower()
    kwargs = {}

    if provider == "google":
        if level := self.config.get("google_thinking_level"):
            kwargs["thinking_level"] = level

    elif provider == "openai":
        if effort := self.config.get("openai_reasoning_effort"):
            kwargs["reasoning_effort"] = effort   # "low" | "medium" | "high"

    elif provider == "anthropic":
        if effort := self.config.get("anthropic_effort"):
            kwargs["effort"] = effort             # "low" | "medium" | "high"

    return kwargs
```

---

## Summary

| Component | Key Design Decision |
|-----------|---------------------|
| **Pipeline** | LangGraph StateGraph with analyst tool-loops, then two sequential debate phases |
| **Debate** | Controlled loops via message count; alternation via `current_response` prefix or `latest_speaker` field |
| **Prompts** | Analysts: tool-use + report generation. Debaters: conversational, evidence-based, counter-targeting. Managers: judge + 5-tier rating enforcer |
| **State** | Nested `TypedDict` for debate states; plain `str` for reports; accumulates across phases without clearing |
| **Tools** | 9 abstract tools routing to yfinance/Alpha Vantage; return formatted prose for LLM consumption |
| **Memory** | Append-only markdown log; Phase A captures, Phase B reflects with outcome data; injected into Portfolio Manager only |
| **Structured Output** | Pydantic schemas with graceful fallback; provider-native methods (tool-use for Anthropic, response_schema for Gemini, function_calling for OpenAI) |
| **LLM Factory** | `deep_think_llm` for decision-makers; `quick_think_llm` for analysts; unified provider abstraction; content normalization across all clients |
