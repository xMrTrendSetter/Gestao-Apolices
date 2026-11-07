from datetime import date, timedelta

from fastapi import Depends
from pydantic import ValidationError

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..dependencies import DbSession
from ..search import filtro_telefone, texto_busca
from ..dependencies import data_referencia
from ..models import Apolice, CancelamentoApolice, Cliente, RenovacaoApolice
from ..schemas import ApoliceAtualizar, ApoliceCancelar, ApoliceCriar, ApoliceRenovar, ApoliceResposta

router = APIRouter(prefix="/apolices", tags=["Apólices"])


@router.post("", response_model=ApoliceResposta, status_code=status.HTTP_201_CREATED)
def cadastrar_apolice(dados: ApoliceCriar, db: DbSession):
    if db.get(Cliente, dados.cliente_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")

    apolice = Apolice(
        **dados.model_dump(exclude={"premio"}),
        premio_centavos=int(dados.premio * 100),
    )
    db.add(apolice)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não foi possível cadastrar: número de apólice já utilizado ou cliente indisponível.",
        ) from error
    db.refresh(apolice)
    return apolice



@router.get("", response_model=list[ApoliceResposta])
def listar_apolices(
    db: DbSession,
    telefone: Annotated[str | None, Query(min_length=1, max_length=25)] = None,
    cliente_id: Annotated[int | None, Query(gt=0)] = None,
    numero: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
    seguradora: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    ramo: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
    cancelada: bool | None = None,
    renovada: bool | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
):
    consulta = select(Apolice)
    if telefone is not None:
        consulta = consulta.join(Cliente, Apolice.cliente_id == Cliente.id).where(filtro_telefone(telefone))
    if cliente_id is not None:
        consulta = consulta.where(Apolice.cliente_id == cliente_id)
    for coluna, valor in [(Apolice.numero, numero), (Apolice.seguradora, seguradora), (Apolice.ramo, ramo)]:
        if valor is not None:
            consulta = consulta.where(coluna.icontains(texto_busca(valor), autoescape=True))
    if cancelada is not None:
        condicao = Apolice.cancelamento.has()
        consulta = consulta.where(condicao if cancelada else ~condicao)
    if renovada is not None:
        condicao = Apolice.renovacao_saida.has()
        consulta = consulta.where(condicao if renovada else ~condicao)
    return db.scalars(consulta.order_by(Apolice.id).offset(offset).limit(limite)).all()



@router.get("/vencidas", response_model=list[ApoliceResposta])
def listar_apolices_vencidas(
    db: DbSession,
    hoje: Annotated[date, Depends(data_referencia)],
    cliente_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
):
    consulta = select(Apolice).where(
        Apolice.fim_vigencia < hoje, ~Apolice.cancelamento.has(), ~Apolice.renovacao_saida.has()
    )
    if cliente_id is not None:
        consulta = consulta.where(Apolice.cliente_id == cliente_id)
    return db.scalars(consulta.order_by(Apolice.fim_vigencia, Apolice.id).offset(offset).limit(limite)).all()



@router.get("/a-vencer", response_model=list[ApoliceResposta])
def listar_apolices_a_vencer(
    db: DbSession,
    hoje: Annotated[date, Depends(data_referencia)],
    dias: Annotated[int, Query(ge=0, le=365)] = 30,
    cliente_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
):
    consulta = select(Apolice).where(
        Apolice.fim_vigencia >= hoje,
        Apolice.fim_vigencia <= hoje + timedelta(days=dias),
        ~Apolice.cancelamento.has(),
        ~Apolice.renovacao_saida.has(),
    )
    if cliente_id is not None:
        consulta = consulta.where(Apolice.cliente_id == cliente_id)
    return db.scalars(consulta.order_by(Apolice.fim_vigencia, Apolice.id).offset(offset).limit(limite)).all()



@router.get("/{apolice_id}", response_model=ApoliceResposta)
def consultar_apolice(apolice_id: Annotated[int, Path(ge=1)], db: DbSession):
    apolice = db.get(Apolice, apolice_id)
    if apolice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Apólice não encontrada.")
    return apolice



@router.patch("/{apolice_id}", response_model=ApoliceResposta)
def atualizar_apolice(apolice_id: Annotated[int, Path(ge=1)], dados: ApoliceAtualizar, db: DbSession):
    apolice = consultar_apolice(apolice_id, db)
    if apolice.cancelada:
        raise HTTPException(status_code=409, detail="Apólice cancelada não pode ser alterada.")
    if apolice.anterior_id is not None or apolice.renovada_por_id is not None:
        raise HTTPException(status_code=409, detail="Apólice vinculada a uma renovação não pode ser editada nesta etapa.")
    alteracoes = dados.model_dump(exclude_unset=True)
    # Valida as datas combinadas com os valores já salvos antes de alterar o modelo.
    try:
        validado = ApoliceCriar.model_validate({
            **{campo: getattr(apolice, campo) for campo in ApoliceCriar.model_fields},
            **alteracoes,
        })
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="Dados inválidos: confira os campos e a vigência.") from error
    if db.get(Cliente, validado.cliente_id) is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    for campo, valor in validado.model_dump(exclude={"premio"}).items():
        setattr(apolice, campo, valor)
    apolice.premio_centavos = int(validado.premio * 100)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Número de apólice já utilizado ou cliente indisponível.") from error
    db.refresh(apolice)
    return apolice



@router.post("/{apolice_id}/cancelamento", response_model=ApoliceResposta)
def cancelar_apolice(apolice_id: Annotated[int, Path(ge=1)], dados: ApoliceCancelar, db: DbSession):
    apolice = consultar_apolice(apolice_id, db)
    if apolice.cancelada:
        raise HTTPException(status_code=409, detail="Apólice já cancelada.")
    if apolice.renovada_por_id is not None:
        raise HTTPException(status_code=409, detail="Apólice já renovada; consulte a apólice sucessora.")
    db.add(CancelamentoApolice(apolice_id=apolice_id, motivo=dados.motivo))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Cancelamento já registrado ou apólice indisponível.") from error
    db.refresh(apolice)
    return apolice



@router.post("/{apolice_id}/renovacao", response_model=ApoliceResposta, status_code=201)
def renovar_apolice(apolice_id: Annotated[int, Path(ge=1)], dados: ApoliceRenovar, db: DbSession):
    anterior = consultar_apolice(apolice_id, db)
    if anterior.cancelada or anterior.renovada_por_id is not None:
        raise HTTPException(status_code=409, detail="Apólice cancelada ou já renovada.")
    if dados.inicio_vigencia < anterior.fim_vigencia:
        raise HTTPException(status_code=422, detail="A renovação deve iniciar no fim da vigência anterior ou depois.")
    nova = Apolice(numero=dados.numero.upper(), cliente_id=anterior.cliente_id,
                  seguradora=anterior.seguradora, ramo=anterior.ramo,
                  inicio_vigencia=dados.inicio_vigencia, fim_vigencia=dados.fim_vigencia,
                  premio_centavos=int(dados.premio * 100))
    try:
        # A nova apólice e o vínculo são gravados na mesma transação.
        db.add(nova)
        db.flush()
        db.add(RenovacaoApolice(anterior_id=anterior.id, nova_id=nova.id))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Número já utilizado ou renovação já registrada.") from error
    db.refresh(nova)
    return nova
