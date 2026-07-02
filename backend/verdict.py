def generate_verdict(stats, strategy_name):
    ret = stats['Return [%]']
    win_rate = stats['Win Rate [%]']
    n_trades = stats['# Trades']
    dd = stats['Max. Drawdown [%]']

    if n_trades == 0:
        return {"action": "HOLD", "message": f"The {strategy_name} strategy found no trade signals in this period — no clear buy or sell opportunity."}

    if ret > 5 and win_rate >= 50:
        action = "BUY"
        message = (f"Over this period, {strategy_name} would have grown your capital by {ret:.1f}%, "
                    f"winning {win_rate:.0f}% of {n_trades} trades. This strategy looks favorable for this stock.")
    elif ret < 0:
        action = "AVOID"
        message = (f"{strategy_name} lost {abs(ret):.1f}% over this period with a max drawdown of {dd:.1f}%. "
                    f"This strategy does not look suitable for this stock right now.")
    else:
        action = "HOLD/CAUTION"
        message = (f"{strategy_name} gave a modest {ret:.1f}% return with {win_rate:.0f}% win rate. "
                    f"Results are mixed — proceed with caution.")

    return {"action": action, "message": message}
