from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator


class ClienteCriar(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    telefone: str | None = Field(default=None, max_length=25)
    ativo: bool = True

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        # A regra do projeto considera o e-mail único sem distinguir maiúsculas.
        return value.casefold()

    @field_validator("telefone")
    @classmethod
    def normalizar_telefone(cls, value: str | None) -> str | None:
        return value or None


class ClienteAtualizar(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # Omitir um campo mantém o valor salvo. Somente telefone aceita null.
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = Field(default=None, max_length=254)
    telefone: str | None = Field(default=None, max_length=25)
    ativo: bool | None = None

    @field_validator("nome", "email", "ativo", mode="before")
    @classmethod
    def rejeitar_nulos(cls, value):
        if value is None:
            raise ValueError("Este campo não pode ser nulo; omita-o para manter o valor atual.")
        return value

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        return value.casefold()

    @field_validator("telefone")
    @classmethod
    def normalizar_telefone(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def exigir_alteracao(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Envie pelo menos um campo para atualizar.")
        return self


class ClienteResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: EmailStr
    telefone: str | None
    ativo: bool


class ApoliceCriar(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    numero: str = Field(min_length=1, max_length=60)
    cliente_id: int = Field(gt=0)
    seguradora: str = Field(min_length=2, max_length=120)
    ramo: str = Field(min_length=2, max_length=60)
    inicio_vigencia: date
    fim_vigencia: date
    premio: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)

    @field_validator("numero")
    @classmethod
    def normalizar_numero(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validar_vigencia(self) -> Self:
        if self.fim_vigencia <= self.inicio_vigencia:
            raise ValueError("O fim da vigência deve ser posterior ao início.")
        return self


class ApoliceResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero: str
    cliente_id: int
    seguradora: str
    ramo: str
    inicio_vigencia: date
    fim_vigencia: date
    premio: Decimal

    anterior_id: int | None = None
    renovada_por_id: int | None = None
    cancelada: bool
    cancelamento: "CancelamentoResposta | None" = None


class CancelamentoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    motivo: str
    registrado_em: datetime  # UTC


class ApoliceCancelar(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    motivo: str = Field(min_length=3, max_length=500)


class ApoliceAtualizar(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    numero: str | None = Field(default=None, min_length=1, max_length=60)
    cliente_id: int | None = Field(default=None, gt=0)
    seguradora: str | None = Field(default=None, min_length=2, max_length=120)
    ramo: str | None = Field(default=None, min_length=2, max_length=60)
    inicio_vigencia: date | None = None
    fim_vigencia: date | None = None
    premio: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def validar_campos(cls, value):
        if isinstance(value, dict) and (not value or any(v is None for v in value.values())):
            raise ValueError("Envie campos preenchidos; omita os que deseja manter.")
        return value


ApoliceResposta.model_rebuild()


class ApoliceRenovar(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    numero: str = Field(min_length=1, max_length=60)
    inicio_vigencia: date
    fim_vigencia: date
    premio: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)

    @model_validator(mode="after")
    def validar_vigencia(self) -> Self:
        if self.fim_vigencia <= self.inicio_vigencia:
            raise ValueError("O fim da vigência deve ser posterior ao início.")
        return self


class UsuarioCriar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    senha: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("nome", mode="before")
    @classmethod
    def limpar_nome(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        return value.casefold()


class LoginEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    senha: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        return value.casefold()


class TokenResposta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UsuarioResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: EmailStr
    ativo: bool
