import os

from dotenv import load_dotenv

load_dotenv(".tmdb-bot.env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
ALLOWED_USERS = {int(x) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()}

if not BOT_TOKEN or not TMDB_API_KEY or not ALLOWED_USERS:
    raise SystemExit("Missing BOT_TOKEN / TMDB_API_KEY / ALLOWED_USERS in .tmdb-bot.env")
