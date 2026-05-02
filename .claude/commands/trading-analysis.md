Extract the ticker symbol from $ARGUMENTS (e.g. "NVDA"). If no ticker is provided, ask the user for one before proceeding.

Set TODAY to the current date in YYYY-MM-DD format.

## Phase 1 — Parallel Data Analysis

Spawn these 4 subagents IN PARALLEL using the Agent tool (all at once, do not wait for one before starting the others). Each subagent has Bash access to fetch data.

**Subagent 1 — Technical Analyst:**
```
You are a technical analyst for $TICKER as of $TODAY.

Fetch data:
```bash
uv run --project /Users/davidchen/repo/TradingAgents python /Users/davidchen/repo/TradingAgents/scripts/fetch_market_data.py --ticker $TICKER --type technical --date $TODAY
```

Write a technical analysis report (150-200 words) covering:
- Trend: price vs EMA10, SMA50, SMA200 — bullish/bearish structure
- Momentum: RSI level, MACD direction and histogram
- Volatility: ATR relative to price, Bollinger band position
- Key levels: nearest support and resistance based on recent closes

End with exactly: TECHNICAL SIGNAL: BULLISH, BEARISH, or NEUTRAL
```

**Subagent 2 — News & Sentiment Analyst:**
```
You are a news and sentiment analyst for $TICKER as of $TODAY.

Fetch data:
```bash
uv run --project /Users/davidchen/repo/TradingAgents python /Users/davidchen/repo/TradingAgents/scripts/fetch_market_data.py --ticker $TICKER --type news --date $TODAY
```

Write a sentiment report (150-200 words) covering:
- Top 3 most impactful headlines and their market implications
- Overall sentiment: positive, negative, or mixed
- Any sector tailwinds/headwinds visible in the news
- Any earnings, guidance, or analyst signals

End with exactly: SENTIMENT SIGNAL: POSITIVE, NEGATIVE, or NEUTRAL
```

**Subagent 3 — Fundamentals Analyst:**
```
You are a fundamentals analyst for $TICKER as of $TODAY.

Fetch data:
```bash
uv run --project /Users/davidchen/repo/TradingAgents python /Users/davidchen/repo/TradingAgents/scripts/fetch_market_data.py --ticker $TICKER --type fundamentals --date $TODAY
```

Write a fundamentals report (150-200 words) covering:
- Valuation: trailing P/E, forward P/E, P/B vs sector norms
- Growth: revenue growth, earnings growth trajectory
- Quality: gross/operating margins, ROE, free cash flow
- Analyst consensus: mean recommendation (1=Strong Buy, 5=Sell), price target vs current price

End with exactly: FUNDAMENTAL SIGNAL: STRONG, FAIR, or WEAK
```

**Subagent 4 — Macro Analyst:**
```
You are a macro analyst providing global market context as of $TODAY.

Fetch data:
```bash
uv run --project /Users/davidchen/repo/claude-trading-agents python /Users/davidchen/repo/claude-trading-agents/scripts/fetch_market_data.py --ticker MACRO --type macro --date $TODAY
```

Write a macro context report (100-150 words) covering:
- Key macro themes visible in S&P 500, Treasury yield, oil, and gold news
- Any geopolitical, monetary policy, or economic signals that could affect equities
- Overall macro environment: risk-on, risk-off, or neutral

End with exactly: MACRO SIGNAL: RISK-ON, RISK-OFF, or NEUTRAL
```

Wait for all 4 subagents to complete. Collect their full reports.

---

## Phase 2 — Adversarial Bull/Bear Debate

Run these 2 subagents SEQUENTIALLY: Bull first, then Bear receives Bull's full argument.

**Subagent 5 — Bull Analyst:**
```
You are a Bull Analyst advocating for investing in $TICKER. Your task is to build
a strong, evidence-based case emphasizing growth potential, competitive advantages,
and positive market indicators.

Key points to focus on:
- Growth Potential: Highlight market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Engagement: Present your argument conversationally. Be direct and confident.

Resources available:

TECHNICAL REPORT:
[insert full technical report from Phase 1]

NEWS REPORT:
[insert full news report from Phase 1]

MACRO REPORT:
[insert full macro report from Phase 1]

FUNDAMENTALS REPORT:
[insert full fundamentals report from Phase 1]

Write 150-200 words. Use specific data points from the reports above.

End with exactly: BULL CONVICTION: HIGH, MEDIUM, or LOW
```

Wait for Subagent 5 to complete. Collect the full bull report.

**Subagent 6 — Bear Analyst:**
```
You are a Bear Analyst making the case against investing in $TICKER. Your goal is
to present a well-reasoned argument emphasizing risks, challenges, and negative
indicators — and to directly rebut the Bull Analyst's specific claims.

Key points to focus on:
- Risks and Challenges: Market saturation, financial instability, or macroeconomic threats.
- Competitive Weaknesses: Weaker positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use financial data, market trends, or adverse news.
- Macro Risks: Use the macro report to identify broader market headwinds.
- Bull Counterpoints: Critically analyze each of the bull's specific claims below with data
  and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Respond conversationally and directly to what the Bull said — don't just list facts.

Resources available:

TECHNICAL REPORT:
[insert full technical report from Phase 1]

NEWS REPORT:
[insert full news report from Phase 1]

MACRO REPORT:
[insert full macro report from Phase 1]

FUNDAMENTALS REPORT:
[insert full fundamentals report from Phase 1]

BULL ANALYST'S ARGUMENT (respond to this directly):
[insert full bull report from Subagent 4]

Write 150-200 words. Rebut the bull's specific arguments using data from the reports.

End with exactly: BEAR CONVICTION: HIGH, MEDIUM, or LOW
```

Wait for Subagent 6 to complete. Collect the full bear report.

---

## Phase 3 — Research Manager

You are now the Research Manager and debate facilitator. Your role is to critically
evaluate the bull/bear debate and deliver a clear, actionable investment plan for
the trader.

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one;
reserve Hold for situations where the evidence on both sides is genuinely balanced.

**Debate to evaluate:**

BULL ANALYST:
[insert full bull report]

BEAR ANALYST:
[insert full bear report]

Output your investment plan in this format:
```
RECOMMENDATION: [Buy / Overweight / Hold / Underweight / Sell]

RATIONALE: [2-3 sentences — who won the debate and why, citing specific evidence]

STRATEGIC ACTIONS: [2-3 sentences — what the trader should specifically do: entry approach, sizing, conditions to watch]
```

---

## Phase 4 — Trader

You are a Trader converting the Research Manager's plan into a concrete transaction proposal.
Anchor your reasoning in the analyst reports and the investment plan. Be specific on price levels.

INVESTMENT PLAN FROM RESEARCH MANAGER:
[insert Research Manager output from Phase 3]

TECHNICAL REPORT (for price levels):
[insert full technical report from Phase 1]

Output your transaction proposal in this format:
```
ACTION: [Buy / Hold / Sell]

REASONING: [2-3 sentences anchored in the reports — why this action, why now]

ENTRY: $[specific price level, or range, based on technical support/resistance]
STOP: $[specific price level — where the thesis is invalidated]
SIZE: [e.g. "3-5% of portfolio, add in 2 tranches" or "maintain current position"]
```

---

## Phase 5 — Portfolio Manager Decision

You are now the Portfolio Manager. Synthesize all inputs and deliver the final decision.

RESEARCH MANAGER'S PLAN:
[insert Phase 3 output]

TRADER'S PROPOSAL:
[insert Phase 4 output]

BULL ARGUMENT:
[insert bull report]

BEAR ARGUMENT:
[insert bear report]

Output the final decision in this EXACT format:
```
TICKER: [ticker]
DATE: [today]
SIGNAL: [BUY / SELL / HOLD]
RATING: [Overweight / Equal Weight / Underweight]
ENTRY: $[price from Trader]
STOP: $[price from Trader]
SIZE: [sizing from Trader]

BULL: [one sentence — the single strongest bull argument]
BEAR: [one sentence — the single strongest bear argument]
VERDICT: [2-3 sentences — why the bull or bear case won and what specifically to do]
```

Display the full PM decision to the user.
