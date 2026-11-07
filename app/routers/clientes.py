from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..dependencies import DbSession
from ..search import filtro_telefone, texto_busca
from ..models import Cliente
from ..schemas import ClienteAtualizar, ClienteCriar, ClienteResposta

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteResposta, status_code=status.HTTP_201_CREATED)
def cadastrar_cliente(dados: ClienteCriar, db: DbSession):
    cliente = Cliente(**dados.model_dump())
    db.add(cliente)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um cliente com esse e-mail.",
        ) from error
    db.refresh(cliente)
    return cliente



@router.get("", response_model=list[ClienteResposta])
def listar_clientes(
    db: DbSession,
    telefone: Annotated[str | None, Query(min_length=1, max_length=25)] = None,
    nome: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    ativo: bool | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
):
    consulta = select(Cliente)
    if telefone is not None:
        consulta = consulta.where(filtro_telefone(telefone))
    if nome is not None:
        consulta = consulta.where(Cliente.nome.icontains(texto_busca(nome), autoescape=True))
    if ativo is not None:
        consulta = consulta.where(Cliente.ativo == ativo)
    return db.scalars(consulta.order_by(Cliente.id).offset(offset).limit(limite)).all()



@router.get("/{cliente_id}", response_model=ClienteResposta)
def consultar_cliente(cliente_id: Annotated[int, Path(ge=1)], db: DbSession):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")
    return cliente



@router.patch("/{cliente_id}", response_model=ClienteResposta)
def atualizar_cliente(
    cliente_id: Annotated[int, Path(ge=1)],
    dados: ClienteAtualizar,
    db: DbSession,
):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")

    # Não envia os valores padrão dos campos omitidos para o banco.
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um cliente com esse e-mail.",
        ) from error
    db.refresh(cliente)
    return cliente
