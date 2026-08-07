"""
backtest.py v2 - параметрленген backtest engine.
Индикаторлар бір рет есептеліп кэштеледі (precompute_symbol_records),
содан кейін кез келген SL/TP/REQUIRED_SIGNALS комбинациясын
индикаторды қайта есептеместен тез симуляциялауға болады.
hyperopt.py осы модульді import етеді.
"""
from collections import defaultdict
from config import config
from engines.bybit_engine import BybitEngine
from engines.indicator_engine import IndicatorEngine

BACKTEST_DAYS = 180
SYMBOLS = config.SYMBOLS
INITIAL_BALANCE = 1000.0
RISK_PER_TRADE = config.RISK_PER_TRADE
MAX_OPEN_TRADES = config.MAX_OPEN_TRADES
TAKER_FEE_PCT = 0.00055

DAY_MS = 24 * 60 * 60 * 1000
H4_MS = 4 * 60 * 60 * 1000

bybit = BybitEngine()
ind_engine = IndicatorEngine()


def compute_macro_bias(df_macro_slice):
    macro_price = df_macro_slice['close'].iloc[-1]
    macro_ema200 = df_macro_slice['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    macro_ema50_series = df_macro_slice['close'].ewm(span=50, adjust=False).mean()
    macro_ema50 = macro_ema50_series.iloc[-1]
    macro_ema50_prev = macro_ema50_series.iloc[-6] if len(macro_ema50_series) > 6 else macro_ema50_series.iloc[0]
    ema50_slope_up = macro_ema50 > macro_ema50_prev
    ema50_slope_down = macro_ema50 < macro_ema50_prev
    long_term_up = macro_price > macro_ema200
    long_term_down = macro_price < macro_ema200
    if long_term_up and not (macro_price < macro_ema50 and ema50_slope_down):
        return 'up'
    elif long_term_down and not (macro_price > macro_ema50 and ema50_slope_up):
        return 'down'
    return 'neutral'


def precompute_symbol_records(symbol, backtest_days=BACKTEST_DAYS):
    macro_days = backtest_days + 220
    trend_days = backtest_days + 40
    signal_days = backtest_days + 15

    df_macro = bybit.get_historical_klines(symbol, config.TIMEFRAMES['macro'], macro_days)
    df_trend = bybit.get_historical_klines(symbol, config.TIMEFRAMES['trend'], trend_days)
    df_signal = bybit.get_historical_klines(symbol, config.TIMEFRAMES['signal'], signal_days)

    if df_macro.empty or df_trend.empty or df_signal.empty:
        return None

    df_macro = df_macro.sort_values('timestamp').reset_index(drop=True)
    df_trend = df_trend.sort_values('timestamp').reset_index(drop=True)
    df_signal = df_signal.sort_values('timestamp').reset_index(drop=True)

    last_ts = df_signal['timestamp'].iloc[-1]
    start_ts = last_ts - backtest_days * DAY_MS

    records = []
    macro_cache, trend_cache = {}, {}

    for i in range(len(df_signal)):
        row = df_signal.iloc[i]
        t = row['timestamp']
        if t < start_ts or i < 199:
            continue

        day_key = t // DAY_MS
        if day_key not in macro_cache:
            m_slice = df_macro[df_macro['timestamp'] <= t].tail(200)
            macro_cache[day_key] = compute_macro_bias(m_slice) if len(m_slice) >= 200 else None
        macro_bias = macro_cache[day_key]

        h4_key = t // H4_MS
        if h4_key not in trend_cache:
            tr_slice = df_trend[df_trend['timestamp'] <= t].tail(200)
            if len(tr_slice) < 200:
                trend_cache[h4_key] = None
            else:
                tind = ind_engine.calculate_all(tr_slice)
                trend_cache[h4_key] = ind_engine.get_signal(tind) if tind else None
        trend_sig = trend_cache[h4_key]

        signal_slice = df_signal.iloc[i - 199:i + 1]
        indicators = ind_engine.calculate_all(signal_slice)
        sig_data = ind_engine.get_signal(indicators) if indicators else None

        records.append({
            't': t,
            'high': row['high'], 'low': row['low'], 'close': row['close'],
            'macro_bias': macro_bias,
            'trend_direction': trend_sig['direction'] if trend_sig else None,
            'sig_direction': sig_data['direction'] if sig_data else 'WAIT',
            'sig_strength': sig_data['strength'] if sig_data else 0,
            'price': indicators.get('price', row['close']) if indicators else row['close'],
            'atr': indicators.get('atr', row['close'] * 0.01) if indicators else row['close'] * 0.01,
            'adx': indicators.get('adx', 0) if indicators else 0,
        })

    return records


class SimTrade:
    def __init__(self, side, entry_price, qty, sl, tp1, tp2, tp3, opened_at, trade_id):
        self.trade_id = trade_id
        self.side = side
        self.entry_price = entry_price
        self.qty = qty
        self.remaining_qty = qty
        self.sl = sl
        self.tp1, self.tp2, self.tp3 = tp1, tp2, tp3
        self.tp1_hit = self.tp2_hit = self.tp3_hit = False
        self.current_sl = None
        self.highest = entry_price
        self.lowest = entry_price
        self.trailing_active = False
        self.opened_at = opened_at

    def update(self, high, low, close, trailing_atr_mult):
        events = []
        atr = close * 0.01

        if self.side == 'BUY':
            self.highest = max(self.highest, high)
        else:
            self.lowest = min(self.lowest, low)

        if not self.tp1_hit:
            hit = (self.side == 'BUY' and high >= self.tp1) or (self.side == 'SELL' and low <= self.tp1)
            if hit:
                self.tp1_hit = True
                close_qty = round(self.qty * config.TP1_CLOSE, 6)
                events.append((close_qty, self.tp1, 'TP1'))
                self.remaining_qty -= close_qty
                self.current_sl = round(self.entry_price * (1.001 if self.side == 'BUY' else 0.999), 6)
                return events

        if self.tp1_hit and not self.tp2_hit:
            hit = (self.side == 'BUY' and high >= self.tp2) or (self.side == 'SELL' and low <= self.tp2)
            if hit:
                self.tp2_hit = True
                close_qty = round(self.qty * config.TP2_CLOSE, 6)
                events.append((close_qty, self.tp2, 'TP2'))
                self.remaining_qty -= close_qty
                self.current_sl = self.tp1
                self.trailing_active = True
                return events

        if self.tp2_hit and not self.tp3_hit:
            hit = (self.side == 'BUY' and high >= self.tp3) or (self.side == 'SELL' and low <= self.tp3)
            if hit:
                self.tp3_hit = True
                close_qty = round(self.remaining_qty, 6)
                events.append((close_qty, self.tp3, 'TP3'))
                self.remaining_qty = 0
                return events

        if self.trailing_active:
            if self.side == 'BUY':
                new_sl = self.highest - atr * trailing_atr_mult
                if self.current_sl is None or new_sl > self.current_sl:
                    self.current_sl = new_sl
            else:
                new_sl = self.lowest + atr * trailing_atr_mult
                if self.current_sl is None or new_sl < self.current_sl:
                    self.current_sl = new_sl

        active_sl = self.current_sl if self.current_sl is not None else self.sl
        hit_sl = (self.side == 'BUY' and low <= active_sl) or (self.side == 'SELL' and high >= active_sl)
        if hit_sl and self.remaining_qty > 0:
            events.append((self.remaining_qty, active_sl, 'SL'))
            self.remaining_qty = 0

        return events


def simulate(records, params, start_ts=None, end_ts=None):
    sl_mult = params.get('sl_mult', 2.0)
    tp1_mult = params.get('tp1_mult', 2.0)
    tp2_mult = params.get('tp2_mult', 3.5)
    tp3_mult = params.get('tp3_mult', 5.0)
    required_signals = params.get('required_signals', config.REQUIRED_SIGNALS)
    trailing_atr_mult = params.get('trailing_atr_mult', config.ATR_MULTIPLIER)

    balance = INITIAL_BALANCE
    equity_curve = []
    trades_log = []
    open_trade = None
    trade_counter = 0

    for rec in records:
        if start_ts is not None and rec['t'] < start_ts:
            continue
        if end_ts is not None and rec['t'] >= end_ts:
            continue

        if open_trade is not None:
            events = open_trade.update(rec['high'], rec['low'], rec['close'], trailing_atr_mult)
            for close_qty, exit_price, reason in events:
                pnl = (exit_price - open_trade.entry_price) * close_qty if open_trade.side == 'BUY' \
                    else (open_trade.entry_price - exit_price) * close_qty
                fee = (open_trade.entry_price * close_qty + exit_price * close_qty) * TAKER_FEE_PCT
                pnl -= fee
                balance += pnl
                trades_log.append({'trade_id': open_trade.trade_id, 'pnl': pnl})
            if open_trade.remaining_qty <= 0:
                open_trade = None
            equity_curve.append(balance)
            continue

        macro_bias = rec['macro_bias']
        trend_direction = rec['trend_direction']
        if macro_bias is None or trend_direction is None:
            equity_curve.append(balance)
            continue

        if rec['sig_direction'] == 'WAIT' or rec['sig_strength'] < required_signals:
            equity_curve.append(balance)
            continue

        direction = rec['sig_direction']
        if direction == 'BUY' and (macro_bias != 'up' or trend_direction == 'SELL'):
            equity_curve.append(balance)
            continue
        if direction == 'SELL' and (macro_bias != 'down' or trend_direction == 'BUY'):
            equity_curve.append(balance)
            continue

        price = rec['price']
        atr = rec['atr']
        min_sl_distance = price * 0.005
        sl_distance = max(atr * sl_mult, min_sl_distance)
        adx = rec['adx']

        if direction == 'BUY':
            stop_loss = round(price - sl_distance, 6)
            tp1 = round(price + atr * tp1_mult, 6)
            tp2 = round(price + atr * tp2_mult, 6)
            tp3 = round(price + atr * tp3_mult, 6)
        else:
            stop_loss = round(price + sl_distance, 6)
            tp1 = round(price - atr * tp1_mult, 6)
            tp2 = round(price - atr * tp2_mult, 6)
            tp3 = round(price - atr * tp3_mult, 6)

        if adx > 40:
            leverage = 8
        elif adx > 25:
            leverage = 5
        else:
            leverage = 3

        risk_amount = balance * (RISK_PER_TRADE / 100)
        price_diff = abs(price - stop_loss)
        if price_diff == 0 or price <= 0:
            equity_curve.append(balance)
            continue
        risk_per_unit = price_diff / price
        position_size = (risk_amount / risk_per_unit) * leverage
        max_position = (balance / max(MAX_OPEN_TRADES, 1)) * leverage * 0.45
        position_size = min(position_size, max_position)
        qty = round(position_size / price, 4)
        if qty <= 0:
            equity_curve.append(balance)
            continue

        trade_counter += 1
        open_trade = SimTrade(direction, price, qty, stop_loss, tp1, tp2, tp3, rec['t'], trade_counter)
        equity_curve.append(balance)

    if open_trade is not None and open_trade.remaining_qty > 0 and records:
        last_close = records[-1]['close']
        pnl = (last_close - open_trade.entry_price) * open_trade.remaining_qty if open_trade.side == 'BUY' \
            else (open_trade.entry_price - last_close) * open_trade.remaining_qty
        fee = (open_trade.entry_price * open_trade.remaining_qty + last_close * open_trade.remaining_qty) * TAKER_FEE_PCT
        pnl -= fee
        balance += pnl
        trades_log.append({'trade_id': open_trade.trade_id, 'pnl': pnl})

    return balance, trades_log, equity_curve


def compute_stats(trades_log, initial_balance, final_balance, equity_curve):
    if not trades_log:
        return None
    grouped = defaultdict(float)
    for t in trades_log:
        grouped[t['trade_id']] += t['pnl']
    pnls = list(grouped.values())
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    win_rate = len(wins) / len(pnls) * 100
    avg_win = (sum(wins) / len(wins)) if wins else 0
    avg_loss = (sum(losses) / len(losses)) if losses else 0
    win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else float('inf')
    total_return_pct = (final_balance - initial_balance) / initial_balance * 100

    peak = initial_balance
    max_dd = 0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {'trades': len(pnls), 'win_rate': win_rate, 'profit_factor': profit_factor,
            'total_return_pct': total_return_pct, 'max_drawdown_pct': max_dd, 'final_balance': final_balance,
            'avg_win': avg_win, 'avg_loss': avg_loss, 'win_loss_ratio': win_loss_ratio}


def main():
    print(f"Backtest: {BACKTEST_DAYS} күн, {len(SYMBOLS)} символ, старт балансы {INITIAL_BALANCE} USDT\n")
    default_params = {'sl_mult': 2.0, 'tp1_mult': 2.0, 'tp2_mult': 3.5, 'tp3_mult': 5.0,
                       'required_signals': config.REQUIRED_SIGNALS, 'trailing_atr_mult': config.ATR_MULTIPLIER}
    for symbol in SYMBOLS:
        print(f"{symbol}: тарихи деректер жүктелуде...")
        records = precompute_symbol_records(symbol)
        if not records:
            print(f"{symbol}: жеткіліксіз дерек")
            continue
        balance, trades_log, equity_curve = simulate(records, default_params)
        stats = compute_stats(trades_log, INITIAL_BALANCE, balance, equity_curve)
        if stats:
            print(f"{symbol}: trades={stats['trades']} winrate={stats['win_rate']:.1f}% "
                  f"PF={stats['profit_factor']:.2f} return={stats['total_return_pct']:+.1f}% "
                  f"maxDD={stats['max_drawdown_pct']:.1f}% avgWin={stats['avg_win']:.2f} "
                  f"avgLoss={stats['avg_loss']:.2f} W/L_ratio={stats['win_loss_ratio']:.2f}")
        else:
            print(f"{symbol}: сделка болмады")


if __name__ == '__main__':
    main()
