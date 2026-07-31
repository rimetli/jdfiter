from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

connect_args: dict[str, object] = {}
if settings.mysql_ssl:
    ssl_options: dict[str, object] = {}
    if settings.mysql_ssl_ca:
        ssl_options["ca"] = settings.mysql_ssl_ca
    connect_args["ssl"] = ssl_options

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=connect_args,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session

