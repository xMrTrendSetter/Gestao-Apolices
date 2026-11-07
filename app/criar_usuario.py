"""Execute python -m app.criar_usuario; a senha não aparece no terminal."""
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from .database import Base, SessionLocal, engine
from . import models  # Registra todas as tabelas antes da inicialização.
from .schemas import UsuarioCriar
from .security import criar_usuario


def main() -> int:
    nome = input("Nome: ")
    email = input("E-mail: ").strip()
    senha = getpass("Senha (12 a 128 caracteres): ")
    confirmacao = getpass("Confirme a senha: ")
    if senha != confirmacao:
        print("As senhas não coincidem. Nenhum usuário criado.")
        return 1
    try:
        dados = UsuarioCriar(nome=nome, email=email, senha=senha)
    except ValidationError as error:
        # Não imprime a entrada dos validadores, que pode incluir a senha.
        for item in error.errors(include_input=False, include_url=False):
            print(f"{'.'.join(str(c) for c in item['loc'])}: {item['msg']}")
        return 1
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        try:
            criar_usuario(db, dados)
        except IntegrityError:
            db.rollback()
            print("Não foi possível criar: e-mail já cadastrado.")
            return 1
    print("Usuário criado. Faça login no Insomnia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
