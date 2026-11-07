"""Login JSON, consulta do usuário e logout da sessão atual."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ..dependencies import DbSession
from ..models import SessaoUsuario, Usuario
from ..schemas import LoginEntrada, TokenResposta, UsuarioResposta
from ..security import TEMPO_SESSAO, autenticar, emitir_token, sessao_atual, usuario_atual

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResposta)
def login(dados: LoginEntrada, db: DbSession, response: Response):
    usuario = autenticar(db, str(dados.email), dados.senha.get_secret_value())
    token = emitir_token(db, usuario)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResposta(access_token=token, expires_in=TEMPO_SESSAO)


@router.get("/me", response_model=UsuarioResposta)
def consultar_usuario(usuario: Annotated[Usuario, Depends(usuario_atual)]):
    return usuario


@router.post("/logout", status_code=204)
def logout(db: DbSession, sessao: Annotated[SessaoUsuario, Depends(sessao_atual)]):
    db.delete(sessao)
    db.commit()
    return Response(status_code=204)
