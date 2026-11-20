import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?serverSelectionTimeoutMS=3000")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "smart_campus")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false").lower() == "true"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
