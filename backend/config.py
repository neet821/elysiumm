"""
Environment-adaptive configuration
Auto-detects Windows/Linux and adjusts paths/settings accordingly
"""
import os
import sys
import platform
from pathlib import Path
from typing import Literal

# Detect operating system
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Auto-detect project root (works on both Windows and Linux)
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    SOURCE_BACKEND_DIR = Path(sys.executable).parent.resolve()
else:
    # Running as script
    SOURCE_BACKEND_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SOURCE_BACKEND_DIR.parent

# Environment type detection
def get_environment() -> Literal["development", "production", "docker"]:
    """Auto-detect environment type"""
    if os.getenv("DOCKER_ENV") == "true":
        return "docker"
    elif IS_WINDOWS or os.path.exists(PROJECT_ROOT / "Laragon"):
        return "development"
    else:
        return "production"

ENV = get_environment()

# Platform-specific settings
class PlatformConfig:
    """Platform-specific configuration"""

    # Project paths (cross-platform)
    PROJECT_ROOT = PROJECT_ROOT
    BACKEND_DIR = SOURCE_BACKEND_DIR
    FRONTEND_DIR = PROJECT_ROOT / "frontend"
    # Keep uploads under backend/uploads so FastAPI static mount and storage are aligned
    UPLOAD_DIR = BACKEND_DIR / "uploads"
    PRIVATE_STORAGE_DIR = Path(
        os.getenv("PRIVATE_STORAGE_DIR", str(BACKEND_DIR / "private_storage"))
    ).expanduser().resolve()
    ADMIN_FILES_STORAGE_DIR = Path(
        os.getenv(
            "ADMIN_FILES_STORAGE_DIR",
            str(PRIVATE_STORAGE_DIR / "admin_files"),
        )
    ).expanduser().resolve()
    # 日志文件直接放在仓库根目录，避免额外 logs/ 目录
    LOGS_DIR = PROJECT_ROOT

    # Database configuration (environment-based)
    if ENV == "docker":
        DB_HOST = os.getenv("DB_HOST", "mysql")
        DB_PORT = int(os.getenv("DB_PORT", "3306"))
    elif ENV == "development":
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = int(os.getenv("DB_PORT", "3306"))
    else:  # production
        DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
        DB_PORT = int(os.getenv("DB_PORT", "3306"))

    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "blue_local_db")

    # Server configuration
    if ENV == "docker":
        HOST = "0.0.0.0"  # Docker needs to listen on all interfaces
        PORT = 8000
    elif ENV == "development":
        HOST = "127.0.0.1"  # Local development
        PORT = 8000
    else:  # production
        HOST = "0.0.0.0"  # Production needs external access
        PORT = int(os.getenv("PORT", "8000"))

    # CORS origins (environment-based)
    if ENV == "development":
        CORS_ORIGINS = [
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8080",
        ]
    else:
        CORS_ORIGINS = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173"
        ).split(",")

    # JWT configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ALGORITHM = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # File upload settings
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB (增加文件大小限制)
    MAX_ADMIN_FILE_SIZE = int(
        os.getenv("MAX_ADMIN_FILE_SIZE", str(100 * 1024 * 1024))
    )
    LIVE_GEOIP_DATABASE = Path(
        os.getenv(
            "LIVE_GEOIP_DATABASE",
            str(PROJECT_ROOT / "runtime" / "geoip" / "city.mmdb"),
        )
    ).expanduser().resolve()
    LIVE_VIEWER_RETENTION_DAYS = int(
        os.getenv("LIVE_VIEWER_RETENTION_DAYS", "90")
    )
    LIVE_SESSION_TTL_SECONDS = int(
        os.getenv("LIVE_SESSION_TTL_SECONDS", "120")
    )
    LIVE_COOKIE_SECURE = os.getenv(
        "LIVE_COOKIE_SECURE",
        "1" if ENV == "production" else "0",
    ).strip().lower() in {"1", "true", "yes", "on"}
    LIVE_MEDIAMTX_API_URL = os.getenv(
        "LIVE_MEDIAMTX_API_URL",
        "http://127.0.0.1:9997",
    ).strip().rstrip("/")
    LIVE_RECORDING_ROOT = Path(
        os.getenv(
            "LIVE_RECORDING_ROOT",
            str(PROJECT_ROOT / "runtime" / "live-recordings"),
        )
    ).expanduser().resolve()
    LIVE_DISK_RESERVE_BYTES = int(
        os.getenv("LIVE_DISK_RESERVE_BYTES", str(5 * 1024**3))
    )
    LIVE_OFFLINE_GRACE_SECONDS = int(
        os.getenv("LIVE_OFFLINE_GRACE_SECONDS", "30")
    )
    LIVE_RTMP_PUBLIC_URL = os.getenv(
        "LIVE_RTMP_PUBLIC_URL",
        "rtmp://127.0.0.1:1935/live",
    ).strip().rstrip("/")
    LIVE_PUBLIC_BASE_URL = os.getenv(
        "LIVE_PUBLIC_BASE_URL",
        "http://127.0.0.1:5173",
    ).strip().rstrip("/")
    PUBLIC_SYNC_STORAGE_DIR = Path(
        os.getenv("PUBLIC_SYNC_STORAGE", str(PROJECT_ROOT / "sync-storage"))
    ).expanduser().resolve()
    MAX_PUBLIC_SYNC_FILE_SIZE = int(
        os.getenv("MAX_PUBLIC_SYNC_FILE_SIZE", str(100 * 1024 * 1024))
    )
    MAX_PUBLIC_SYNC_CHUNK_SIZE = int(
        os.getenv("MAX_PUBLIC_SYNC_CHUNK_SIZE", str(8 * 1024 * 1024))
    )
    MAX_PUBLIC_SYNC_DEVICE_BYTES = int(
        os.getenv("MAX_PUBLIC_SYNC_DEVICE_BYTES", str(5 * 1024 * 1024 * 1024))
    )
    PUBLIC_SYNC_UPLOAD_TTL_SECONDS = int(
        os.getenv("PUBLIC_SYNC_UPLOAD_TTL_SECONDS", str(24 * 60 * 60))
    )
    ALLOWED_EXTENSIONS = {
        # 图片格式
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg",
        # 视频格式
        ".mp4", ".webm", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".m4v",
        ".3gp", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".vob",
        # 音频格式
        ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac"
    }

    # Avatar upload settings
    AVATAR_UPLOAD_DIR = UPLOAD_DIR / "avatars"
    MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if ENV == "production" else "DEBUG")

    # Provider-neutral music catalog. Player clients never receive provider cookies.
    MUSIC_PROVIDER_BASE_URL = os.getenv(
        "MUSIC_PROVIDER_BASE_URL",
        "http://127.0.0.1:3000",
    ).rstrip("/")
    MUSIC_PROVIDER_ADMIN_TOKEN = os.getenv("MUSIC_PROVIDER_ADMIN_TOKEN", "").strip()
    MUSIC_PROVIDER_TIMEOUT_SECONDS = float(
        os.getenv("MUSIC_PROVIDER_TIMEOUT_SECONDS", "5")
    )
    AUDIUS_API_BASE_URL = os.getenv(
        "AUDIUS_API_BASE_URL",
        "https://api.audius.co/v1",
    ).rstrip("/")
    KAVITA_PUBLIC_BASE_URL = os.getenv("KAVITA_PUBLIC_BASE_URL", "").strip().rstrip("/")
    RAINDROP_PUBLIC_URL = os.getenv("RAINDROP_PUBLIC_URL", "").strip()
    TMDB_API_READ_TOKEN = os.getenv("TMDB_API_READ_TOKEN", "").strip()
    GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "").strip()
    IGDB_CLIENT_ID = os.getenv("IGDB_CLIENT_ID", "").strip()
    IGDB_CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET", "").strip()
    METADATA_REQUEST_USER_AGENT = os.getenv(
        "METADATA_REQUEST_USER_AGENT",
        "Elysium/1.0 (https://elysiumm.top)",
    ).strip()
    METADATA_REQUEST_TIMEOUT_SECONDS = float(
        os.getenv("METADATA_REQUEST_TIMEOUT_SECONDS", "8")
    )
    EXTERNAL_MEDIA_DOH_URL = os.getenv(
        "EXTERNAL_MEDIA_DOH_URL",
        "https://cloudflare-dns.com/dns-query",
    ).strip()
    EXTERNAL_MEDIA_DOH_URLS = tuple(
        value.strip()
        for value in os.getenv(
            "EXTERNAL_MEDIA_DOH_URLS",
            "https://cloudflare-dns.com/dns-query,https://dns.google/resolve",
        ).split(",")
        if value.strip()
    )

    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        # 只确保上传目录存在，日志文件直接放根目录
        for dir_path in [
            cls.UPLOAD_DIR,
            cls.AVATAR_UPLOAD_DIR,
            cls.ADMIN_FILES_STORAGE_DIR,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_database_url(cls) -> str:
        """Get database connection URL"""
        return (
            f"mysql+pymysql://{cls.DB_USER}:{cls.DB_PASSWORD}"
            f"@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        )

    @classmethod
    def print_config(cls):
        """Print current configuration (for debugging)"""
        print("=" * 60)
        print(f"🖥️  Environment: {ENV}")
        print(f"🔧 Platform: {platform.system()} {platform.release()}")
        print(f"📁 Project Root: {cls.PROJECT_ROOT}")
        print(f"🗄️  Database: {cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}")
        print(f"🌐 Server: {cls.HOST}:{cls.PORT}")
        print(f"🔐 CORS Origins: {cls.CORS_ORIGINS}")
        print(f"📝 Log Level: {cls.LOG_LEVEL}")
        print("=" * 60)

# Create directories on import
PlatformConfig.ensure_directories()

# Export for easy import
config = PlatformConfig

if __name__ == "__main__":
    # Test configuration detection
    config.print_config()
