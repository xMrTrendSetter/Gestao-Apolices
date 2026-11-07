"""Filtros compartilhados pelas consultas de clientes e apólices."""
import re

from fastapi import HTTPException
from sqlalchemy import func

from .models import Cliente


def texto_busca(valor: str) -> str:
    valor = valor.strip()
    if not valor:
        raise HTTPException(status_code=422, detail="O texto da busca não pode estar vazio.")
    return valor



def filtro_telefone(valor: str):
    """Compara o número completo, ignorando apenas caracteres de formatação."""
    if not re.fullmatch(r"[0-9()+. \t\r\n-]+", valor):
        raise HTTPException(status_code=422, detail="Informe um telefone com dígitos e formatação válida.")
    digitos = re.sub(r"[^0-9]", "", valor)
    if not digitos:
        raise HTTPException(status_code=422, detail="O telefone deve conter dígitos.")
    coluna = Cliente.telefone
    for caractere in "()+.- \t\r\n":
        coluna = func.replace(coluna, caractere, "")
    return coluna == digitos
