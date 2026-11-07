from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = f"sqlite:///{(PROJECT_DIR / 'gestao_apolices.db').as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@event.listens_for(engine, "connect")
def habilitar_chaves_estrangeiras(dbapi_connection, connection_record):
    """Faz o SQLite exigir que o cliente vinculado à apólice exista."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    """Abre uma sessão por requisição e a fecha mesmo quando ocorre um erro."""
    with SessionLocal() as db:
        yield db
