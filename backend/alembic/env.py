import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL 환경변수가 필요합니다 (backend/.env 참고).")

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()
