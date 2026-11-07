"""Dependências compartilhadas pelas rotas."""
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from .database import get_db

DbSession = Annotated[Session, Depends(get_db)]


def data_referencia() -> date:
    """Data civil de Brasília (UTC-3), independente do fuso do servidor."""
    return datetime.now(timezone(timedelta(hours=-3))).date()
