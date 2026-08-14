from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量 (明确指定 .env 文件路径)
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# 导入配置
from config import PlatformConfig

config = PlatformConfig()

# 数据库连接 URL (从配置读取)
# 如果 DATABASE_URL 为空或未设置，使用分别配置的参数
database_url_from_env = os.getenv("DATABASE_URL", "").strip()
if database_url_from_env:
    SQLALCHEMY_DATABASE_URL = database_url_from_env
else:
    SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"

# SQLite 需要禁用 check_same_thread；MySQL 等保持默认
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # 防止连接断开
    pool_recycle=1800,   # 30分钟回收一次连接
    pool_size=10,        # 连接池大小
    max_overflow=20,     # 超出pool_size后可创建的连接数
    pool_timeout=30,     # 获取连接的超时时间
    echo=False,          # 不打印SQL语句(生产环境)
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
