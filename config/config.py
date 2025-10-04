from dataclasses import dataclass

from dotenv import load_dotenv

from .base import getenv, ImproperlyConfigured


@dataclass
class TelegramBotConfig:
    token: str

@dataclass
class DjangoApiBase:
    token_api: str

@dataclass
class DjangoApiUrl:
    token_url: str

@dataclass
class DjangoApiToken:
    token_django: str

@dataclass
class AdminId:
    id: str

@dataclass
class Config:
    tg_bot: TelegramBotConfig
    django_api_base: DjangoApiBase
    django_api_url: DjangoApiUrl
    django_api_token: DjangoApiToken
    admin_id: AdminId

def load_config() -> Config:
    # Parse a `.env` file and load the variables into environment valriables
    load_dotenv()

    return Config(
        tg_bot=TelegramBotConfig(token=getenv("BOT_TOKEN")),
        django_api_base=DjangoApiBase(token_api=getenv("API_BASE")),
        django_api_url=DjangoApiUrl(token_url=getenv("API_URL")),
        django_api_token=DjangoApiToken(token_django=getenv("API_TOKEN")),
        admin_id=AdminId(id=getenv("ADMIN_TG_IDS")),
    )
