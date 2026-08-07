import os
from dotenv import load_dotenv

# .env файлының нақты орнын көрсетіп жүктеу
base_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path=env_path)

class Config:
    # Биржа параметрлері
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
    BYBIT_SECRET_KEY = os.getenv("BYBIT_SECRET_KEY", "")
    TESTNET = os.getenv("TESTNET", "True").lower() in ('true', '1', 't')
    
    # Саудаланатын жұптар
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    
    # Тәуекелді басқару (Risk Management)
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "1.0"))
    MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "3"))
    MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "5.0"))
    
    # Леверидж шектеулері
    LEVERAGE_LOW = 5
    LEVERAGE_MEDIUM = 8
    LEVERAGE_HIGH = 12
    
    # Тейк-Профит үлестері
    TP1_CLOSE = 0.50
    TP2_CLOSE = 0.30
    TP3_CLOSE = 0.20
    
    ATR_MULTIPLIER = 2.0
    ATR_NEWS_MULTIPLIER = 3.0
    
    # API Кілттері
    CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

config = Config()

# --- Мультитаймфрейм және сигнал параметрлері ---
Config.TIMEFRAMES = {
    'macro': 'D',      # 1D - бас бағыт (macro bias)
    'trend': '240',    # 4H - тренд растауы
    'signal': '60',    # 1H - негізгі сигнал (voting осында)
    'entry': '15'      # 15M - кіру дәлдігі
}
Config.REQUIRED_SIGNALS = int(os.getenv("REQUIRED_SIGNALS", "3"))
Config.FIB_LOOKBACK = 100
Config.PIVOT_LEFT = 3
Config.PIVOT_RIGHT = 3
config = Config()

# --- Тәуекел басқарудың қосымша параметрлері ---
Config.MAX_TRADES_PER_DIRECTION = int(os.getenv("MAX_TRADES_PER_DIRECTION", "2"))
Config.MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
Config.CONSECUTIVE_LOSS_COOLDOWN_MIN = int(os.getenv("CONSECUTIVE_LOSS_COOLDOWN_MIN", "60"))
config = Config()

# --- Волатильділік, funding, order параметрлері ---
Config.MIN_ATR_PERCENT = float(os.getenv("MIN_ATR_PERCENT", "0.15"))
Config.MAX_FUNDING_RATE = float(os.getenv("MAX_FUNDING_RATE", "0.03"))
Config.USE_LIMIT_ENTRY = os.getenv("USE_LIMIT_ENTRY", "True").lower() in ('true', '1', 't')
Config.LIMIT_ORDER_TIMEOUT_SEC = int(os.getenv("LIMIT_ORDER_TIMEOUT_SEC", "20"))
Config.LIMIT_ORDER_OFFSET_PCT = float(os.getenv("LIMIT_ORDER_OFFSET_PCT", "0.05"))
config = Config()
