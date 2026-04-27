import asyncio
from app.models.engine import init_db_engine, get_async_session_factory
from sqlalchemy import text

async def test():
    init_db_engine()
    session_factory = get_async_session_factory()
    async with session_factory() as s:
        r = await s.execute(text('SELECT 1'))
        print('DB OK:', r.scalar())

asyncio.run(test())
