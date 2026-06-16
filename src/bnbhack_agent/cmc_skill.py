from __future__ import annotations

import json
from pathlib import Path

from .models import ResearchSummary


def export_cmc_skill_spec(summary: ResearchSummary, *, include_monolit: bool = False) -> str:
    best = summary.best
    strategy = best.strategy
    result = best.result
    monolit_line = (
        "- Optional enrichment: **Monolit MCP** wallet-flow/liquidity anomaly veto. CMC remains the required primary data layer; Monolit is disabled unless `MONOLIT_MCP_URL` is configured.\n"
        if include_monolit
        else ""
    )
    spec = {
        "skill_name": f"{strategy.name}_cmc_strategy_skill",
        "track": "Track 2 — Strategy Skills",
        "backtestable": True,
        "primary_sponsor_capability": "CoinMarketCap Data API / CMC MCP",
        "upgrade_path": "Trust Wallet Agent Kit quote-only/execution adapter + BNB Chain venue policy for Track 1",
        "symbol": summary.symbol,
        "parameters": strategy.parameters,
        "entry_rules": strategy.entry_rules,
        "exit_rules": strategy.exit_rules,
        "risk_policy": strategy.risk_policy,
        "validation_metrics": result.to_dict(),
    }
    return f"""# CMC Strategy Skill Spec — {strategy.name}

## Hackathon fit

- Track: **Track 2 — Strategy Skills**.
- Required sponsor capability: **CoinMarketCap Data API / CMC MCP** for OHLCV, technical indicators, sentiment/derivatives/narratives when credentials are present.
- Backtestable: **yes** — deterministic signals + bar-by-bar replay + exported metrics.
- Track 1 upgrade: **Trust Wallet Agent Kit** can consume accepted signals through quote-only or execution mode; BNB Chain venue policy keeps outputs BSC/PancakeSwap/BSC-perps compatible.
{monolit_line}
## Strategy thesis

{strategy.description}

## Entry rules

{chr(10).join(f"- {rule}" for rule in strategy.entry_rules)}

## Exit rules

{chr(10).join(f"- {rule}" for rule in strategy.exit_rules)}

## Risk policy

```json
{json.dumps(strategy.risk_policy, indent=2)}
```

## Backtest metrics

- Total return: `{result.total_return:.2%}`
- Sharpe: `{result.sharpe:.2f}`
- Max drawdown: `{result.max_drawdown:.2%}`
- Win rate: `{result.win_rate:.2%}`
- Turnover: `{result.turnover}`
- Exposure: `{result.exposure:.2%}`
- Rule violations: `{len(result.rule_violations)}`

## Machine-readable skill manifest

```json
{json.dumps(spec, indent=2)}
```
"""


def save_cmc_skill_spec(summary: ResearchSummary, out_path: Path, *, include_monolit: bool = False) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(export_cmc_skill_spec(summary, include_monolit=include_monolit), encoding="utf-8")
    return out_path
