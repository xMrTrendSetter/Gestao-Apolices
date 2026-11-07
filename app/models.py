from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    telefone: Mapped[str | None] = mapped_column(String(25), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Apolice(Base):
    __tablename__ = "apolices"
    __table_args__ = (
        CheckConstraint("premio_centavos >= 0", name="ck_apolices_premio_nao_negativo"),
        CheckConstraint("fim_vigencia > inicio_vigencia", name="ck_apolices_vigencia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    seguradora: Mapped[str] = mapped_column(String(120), nullable=False)
    ramo: Mapped[str] = mapped_column(String(60), nullable=False)
    inicio_vigencia: Mapped[date] = mapped_column(Date, nullable=False)
    fim_vigencia: Mapped[date] = mapped_column(Date, nullable=False)
    # Inteiro em centavos evita aproximação de ponto flutuante no SQLite.
    premio_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def premio(self) -> Decimal:
        return Decimal(self.premio_centavos).scaleb(-2)

    cancelamento: Mapped["CancelamentoApolice | None"] = relationship(uselist=False)

    @property
    def cancelada(self) -> bool:
        return self.cancelamento is not None


    renovacao_saida: Mapped["RenovacaoApolice | None"] = relationship(foreign_keys="RenovacaoApolice.anterior_id", uselist=False)
    renovacao_entrada: Mapped["RenovacaoApolice | None"] = relationship(foreign_keys="RenovacaoApolice.nova_id", uselist=False)

    @property
    def anterior_id(self) -> int | None:
        return self.renovacao_entrada.anterior_id if self.renovacao_entrada else None

    @property
    def renovada_por_id(self) -> int | None:
        return self.renovacao_saida.nova_id if self.renovacao_saida else None


class CancelamentoApolice(Base):
    __tablename__ = "cancelamentos_apolices"

    apolice_id: Mapped[int] = mapped_column(ForeignKey("apolices.id"), primary_key=True)
    motivo: Mapped[str] = mapped_column(String(500), nullable=False)
    registrado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


class RenovacaoApolice(Base):
    __tablename__ = "renovacoes_apolices"
    __table_args__ = (CheckConstraint("anterior_id != nova_id", name="ck_renovacao_distinta"),)
    anterior_id: Mapped[int] = mapped_column(ForeignKey("apolices.id"), primary_key=True)
    nova_id: Mapped[int] = mapped_column(ForeignKey("apolices.id"), unique=True, nullable=False)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SessaoUsuario(Base):
    __tablename__ = "sessoes_usuarios"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
