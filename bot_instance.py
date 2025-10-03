from aiogram import Bot, Dispatcher
from config import Config, load_config

config: Config = load_config()
bot: Bot = Bot(token=config.tg_bot.token)