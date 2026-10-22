import os


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    PORT = _int_env("PORT", 3000)
    MONGODB_URI = os.environ.get(
        "MONGODB_URI",
        "mongodb://127.0.0.1:27017/dm_questionnaire",
    )
    SESSION_DAYS = _int_env("SESSION_DAYS", 7)
    RESPONDENT_SECRET = os.environ.get(
        "RESPONDENT_SECRET",
        "development-only-change-me",
    )
    SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "false").lower() == "true"
    COOKIE_NAME = os.environ.get("COOKIE_NAME", "dm_session")
    PRODUCTION = os.environ.get("FLASK_ENV") == "production"
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"


if Config.PRODUCTION and Config.RESPONDENT_SECRET == "development-only-change-me":
    raise RuntimeError("生产环境必须设置 RESPONDENT_SECRET")
