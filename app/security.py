"""Senhas Argon2 e sessões Bearer opacas com expiração e revogação."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .dependencies import DbSession
from .models import SessaoUsuario, Usuario
from .schemas import UsuarioCriar

password_hash = PasswordHash.recommended()
HASH_FICTICIO = password_hash.hash(secrets.token_urlsafe(32))
TEMPO_SESSAO = 30 * 60
bearer = HTTPBearer(auto_error=False)


def agora_utc() -> datetime:
    # SQLite armazena esta data em UTC sem informação de fuso.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def resumo_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def criar_usuario(db: Session, dados: UsuarioCriar) -> Usuario:
    usuario = Usuario(nome=dados.nome, email=str(dados.email), senha_hash=password_hash.hash(dados.senha.get_secret_value()))
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def erro_autenticacao() -> HTTPException:
    return HTTPException(status_code=401, detail="Credenciais inválidas ou sessão expirada.",
                         headers={"WWW-Authenticate": "Bearer"})


def autenticar(db: Session, email: str, senha: str) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    hash_salvo = usuario.senha_hash if usuario else HASH_FICTICIO
    correta = password_hash.verify(senha, hash_salvo)
    if not correta or usuario is None or not usuario.ativo:
        raise erro_autenticacao()
    return usuario


def emitir_token(db: Session, usuario: Usuario) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessaoUsuario(token_hash=resumo_token(token), usuario_id=usuario.id,
                        expira_em=agora_utc() + timedelta(seconds=TEMPO_SESSAO)))
    db.commit()
    return token


def sessao_atual(
    db: DbSession,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SessaoUsuario:
    if credenciais is None or not 40 <= len(credenciais.credentials) <= 128:
        raise erro_autenticacao()
    sessao = db.get(SessaoUsuario, resumo_token(credenciais.credentials))
    if sessao is None or sessao.expira_em <= agora_utc():
        raise erro_autenticacao()
    usuario = db.get(Usuario, sessao.usuario_id)
    if usuario is None or not usuario.ativo:
        raise erro_autenticacao()
    return sessao


def usuario_atual(db: DbSession, sessao: Annotated[SessaoUsuario, Depends(sessao_atual)]) -> Usuario:
    usuario = db.get(Usuario, sessao.usuario_id)
    if usuario is None:
        raise erro_autenticacao()
    return usuario
