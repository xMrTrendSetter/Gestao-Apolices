"""Inicialização da API e registro dos roteadores."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import Base, engine
from .routers import apolices, auth, clientes
from .security import usuario_atual


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield



app = FastAPI(title="Gestão de Apólices", lifespan=lifespan)


@app.get("/health", tags=["Status"])
def health():
    return {"status": "ok"}



app.include_router(auth.router)
app.include_router(clientes.router, dependencies=[Depends(usuario_atual)])
app.include_router(apolices.router, dependencies=[Depends(usuario_atual)])


@app.exception_handler(RequestValidationError)
async def tratar_validacao(request: Request, error: RequestValidationError):
    if request.url.path.startswith("/auth/"):
        # Os erros padrão podem repetir o corpo recebido, inclusive a senha.
        erros = [{chave: item[chave] for chave in ("type", "loc", "msg")} for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": erros})
    return await request_validation_exception_handler(request, error)
