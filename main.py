import asyncio
import logging
import sys
from config import config
from engines.trading_engine import TradingEngine
from engines.news_engine import NewsEngine
from bot.telegram_bot import TelegramBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/root/trading_bot/trading_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Main")

async def main():
    logger.info("🚀 Trading Bot іске қосылуда...")
    trading_engine = TradingEngine()
    news_engine = NewsEngine()
    
    bot = TelegramBot(trading_engine, news_engine)
    trading_engine.set_telegram_callback(bot.send_message)

    async def on_news_update(news_data: dict):
        trading_engine.set_news_data(news_data)

    logger.info("Бот пен Сауда қозғалтқышын іске қосу...")
    await asyncio.gather(
        bot.run(),
        trading_engine.start(),
        news_engine.monitor(callback=on_news_update)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот қолмен тоқтатылды.")
