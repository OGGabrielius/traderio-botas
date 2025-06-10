import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
import os

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = int(os.environ['CHAT_ID'])
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']
SYMBOL = "ETHUSDT"
TIMEFRAMES = [("4h", "4H"), ("1d", "1D")]
SIGNAL_FILE = "last_signal.txt"

def get_binance_klines(symbol, interval, limit=500):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        print(f"Klaida gaunant duomenis: {e}")
        return pd.DataFrame()

def calculate_indicators(df):
    df['EMA_50'] = df['close'].ewm(span=50).mean()
    df['EMA_200'] = df['close'].ewm(span=200).mean()
    df['RSI'] = 100 - (100 / (1 + df['close'].pct_change().add(1).rolling(14).apply(lambda x: (x[x > 1].mean() or 0.01) / (x[x <= 1].mean() or 0.01))))
    df['ATR'] = (df['high'] - df['low']).rolling(14).mean()
    return df

def fibonacci_levels(df):
    recent_high = df['high'].iloc[-20:].max()
    recent_low = df['low'].iloc[-20:].min()
    diff = recent_high - recent_low
    return {
        "0.0": round(recent_high, 2),
        "50.0": round(recent_high - 0.5 * diff, 2),
        "100.0": round(recent_low, 2)
    }

def detect_signal(df):
    latest = df.iloc[-1]
    fib = fibonacci_levels(df)
    if latest['EMA_50'] > latest['EMA_200'] and 30 < latest['RSI'] < 70 and latest['close'] > fib['50.0']:
        return "long"
    elif latest['EMA_50'] < latest['EMA_200'] and latest['RSI'] > 30 and latest['close'] < fib['50.0']:
        return "short"
    return "none"

def format_message(df, tf_name, signal_type):
    latest = df.iloc[-1]
    fib = fibonacci_levels(df)
    close = round(latest['close'], 2)
    atr = latest['ATR']
    sl = round(close - 1.5 * atr, 2)
    tp1 = round(close + (close - sl), 2)
    if signal_type == "long":
        signal = "[BUY] Pirkimo signalas"
    elif signal_type == "short":
        signal = "[SELL] Pardavimo signalas"
    else:
        signal = "[NONE] Nėra signalo"

    msg = f"ETH/USDT analizė ({tf_name})\n{signal}\nKaina: {close}\nSL: {sl} | TP1: {tp1}\nEMA50: {round(latest['EMA_50'],2)} | EMA200: {round(latest['EMA_200'],2)}\nRSI: {round(latest['RSI'],2)}\nFibonacci 0%: {fib['0.0']} | 50%: {fib['50.0']} | 100%: {fib['100.0']}\n#NeFinansinisPatarimas"
    return msg

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

def send_discord(msg):
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})

def is_weekend():
    return datetime.now(pytz.timezone('Europe/Vilnius')).weekday() in [5, 6]

def load_last_signal(tf):
    if os.path.exists(SIGNAL_FILE):
        with open(SIGNAL_FILE, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if tf in line:
                    return line.strip().split(":")[1]
    return "none"

def save_signal(tf, signal_type):
    lines = []
    if os.path.exists(SIGNAL_FILE):
        with open(SIGNAL_FILE, 'r') as f:
            lines = f.readlines()
    updated = False
    with open(SIGNAL_FILE, 'w') as f:
        for line in lines:
            if tf in line:
                f.write(f"{tf}:{signal_type}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"{tf}:{signal_type}\n")

def main():
    if is_weekend():
        print("Savaitgalis – signalai nesiunčiami.")
        return
    for tf, name in TIMEFRAMES:
        df = get_binance_klines(SYMBOL, tf)
        if df.empty:
            print(f"[{name}] Binance negrąžino duomenų – praleidžiam.")
            continue
        df = calculate_indicators(df)
        signal_type = detect_signal(df)
        last_signal = load_last_signal(tf)
        if signal_type != last_signal and signal_type != "none":
            msg = format_message(df, name, signal_type)
            send_telegram(msg)
            send_discord(msg)
            save_signal(tf, signal_type)
        else:
            print(f"[{name}] Nėra naujo signalo – nieko nesiunčiame.")

if __name__ == "__main__":
    main()