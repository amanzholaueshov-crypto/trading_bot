"""
hyperopt.py - Freqtrade-тің Hyperopt идеясы: SL/TP/REQUIRED_SIGNALS
параметрлерін қолмен біреу-біреулеп сынаудың орнына, grid search
арқылы жүйелі түрде іздейді. Overfitting-тен қорғану үшін
train (оптимизация) / test (мүлдем көрмеген, out-of-sample) бөлінеді -
таңдау тек TEST нәтижесі бойынша жасалады.
"""
from backtest import (SYMBOLS, INITIAL_BALANCE, precompute_symbol_records,
                       simulate, compute_stats, DAY_MS)

TRAIN_DAYS = 120
TEST_DAYS = 60

SL_MULTS = [1.5, 2.0, 2.5]
TP1_MULTS = [2.0, 3.0, 4.0]
REQUIRED_SIGNALS_LIST = [3, 4]


def main():
    print(f"Hyperopt: train={TRAIN_DAYS}kun / test={TEST_DAYS}kun (out-of-sample)\n")

    all_records = {}
    for symbol in SYMBOLS:
        print(f"{symbol}: tarihi derekter juktelude...")
        records = precompute_symbol_records(symbol, backtest_days=TRAIN_DAYS + TEST_DAYS)
        if records:
            all_records[symbol] = records

    if not all_records:
        print("Derek jok, toktatyldy.")
        return

    last_t = max(r[-1]['t'] for r in all_records.values())
    test_start_ts = last_t - TEST_DAYS * DAY_MS

    results = []
    for sl_mult in SL_MULTS:
        for tp1_mult in TP1_MULTS:
            for req_sig in REQUIRED_SIGNALS_LIST:
                params = {'sl_mult': sl_mult, 'tp1_mult': tp1_mult,
                          'tp2_mult': round(tp1_mult * 1.75, 2), 'tp3_mult': round(tp1_mult * 2.5, 2),
                          'required_signals': req_sig, 'trailing_atr_mult': 2.0}

                train_pf_list, test_pf_list, test_dd_list = [], [], []
                total_test_trades = 0

                for symbol, records in all_records.items():
                    bal_tr, log_tr, eq_tr = simulate(records, params, end_ts=test_start_ts)
                    stats_tr = compute_stats(log_tr, INITIAL_BALANCE, bal_tr, eq_tr)

                    bal_te, log_te, eq_te = simulate(records, params, start_ts=test_start_ts)
                    stats_te = compute_stats(log_te, INITIAL_BALANCE, bal_te, eq_te)

                    if stats_tr:
                        train_pf_list.append(stats_tr['profit_factor'])
                    if stats_te:
                        test_pf_list.append(stats_te['profit_factor'])
                        test_dd_list.append(stats_te['max_drawdown_pct'])
                        total_test_trades += stats_te['trades']

                if not test_pf_list:
                    continue

                avg_train_pf = sum(train_pf_list) / len(train_pf_list) if train_pf_list else 0
                avg_test_pf = sum(test_pf_list) / len(test_pf_list)
                avg_test_dd = sum(test_dd_list) / len(test_dd_list)

                results.append({
                    'sl_mult': sl_mult, 'tp1_mult': tp1_mult, 'required_signals': req_sig,
                    'avg_train_pf': avg_train_pf, 'avg_test_pf': avg_test_pf,
                    'avg_test_dd': avg_test_dd, 'total_test_trades': total_test_trades,
                })

    results.sort(key=lambda r: r['avg_test_pf'], reverse=True)

    print("\n=== TOP 10 (out-of-sample TEST PF boyynsha) ===")
    print(f"{'SL':>5} {'TP1':>5} {'ReqSig':>7} {'TrainPF':>8} {'TestPF':>8} {'TestDD':>8} {'TestTrades':>11}")
    for r in results[:10]:
        print(f"{r['sl_mult']:>5} {r['tp1_mult']:>5} {r['required_signals']:>7} "
              f"{r['avg_train_pf']:>8.2f} {r['avg_test_pf']:>8.2f} {r['avg_test_dd']:>8.1f} "
              f"{r['total_test_trades']:>11}")


if __name__ == '__main__':
    main()
