from typing import List, Dict, Any
from models import BacktestTrade

def calculate_backtest_stats(trades: List[BacktestTrade]) -> Dict[str, Any]:
    """
    Calculates key metrics for a list of backtest trades.
    """
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
        }
    
    wins = sum(1 for t in trades if t.status.lower() == "win")
    losses = total_trades - wins
    winrate = (wins / total_trades) * 100
    total_pnl = sum(t.pnl for t in trades)
    avg_pnl = total_pnl / total_trades

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "winrate": round(winrate, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
    }
