"""Teste das rotas com SQLite em memória, sem modificar os clientes cadastrados."""
import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db, habilitar_chaves_estrangeiras
from app.main import app
from app.dependencies import data_referencia
from app.models import Apolice, SessaoUsuario, Usuario
from app.schemas import UsuarioCriar
from app.security import agora_utc, criar_usuario, resumo_token

test_engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
event.listen(test_engine, "connect", habilitar_chaves_estrangeiras)
Base.metadata.create_all(test_engine)
TestSession = sessionmaker(bind=test_engine)


def test_db():
    with TestSession() as db:
        yield db


TOKEN = None
AUTOMATICO = object()


async def request(method, path, payload=None, query="", token=AUTOMATICO):
    messages = []
    if token is AUTOMATICO:
        token = TOKEN
    headers = [(b"content-type", b"application/json")]
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    body = b"" if payload is None else json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
               "http_version": "1.1", "method": method, "scheme": "http", "path": path,
               "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
               "headers": headers, "client": ("127.0.0.1", 1),
               "server": ("test", 80)}, receive, send)
    code = next(m["status"] for m in messages if m["type"] == "http.response.start")
    raw = b"".join(m.get("body", b"") for m in messages)
    data = json.loads(raw) if raw else None
    return code, data


async def testar_apolices():
    assert await request("GET", "/apolices") == (200, [])
    cliente_antes = await request("GET", "/clientes/1")
    payload = {"numero": " ap-2026-0001 ", "cliente_id": 1,
               "seguradora": " Seguradora Exemplo ", "ramo": " Automóvel ",
               "inicio_vigencia": "2026-11-07", "fim_vigencia": "2027-11-07",
               "premio": "1250.50"}
    esperado = dict(payload, anterior_id=None, renovada_por_id=None, cancelada=False, cancelamento=None, id=1, numero="AP-2026-0001", seguradora="Seguradora Exemplo", ramo="Automóvel")
    assert await request("POST", "/apolices", payload) == (201, esperado)
    assert await request("GET", "/apolices/1") == (200, esperado)
    assert await request("GET", "/apolices") == (200, [esperado])
    assert (await request("POST", "/apolices", dict(payload, numero="AP-2026-0001")))[0] == 409
    assert (await request("POST", "/apolices", dict(payload, numero="OUTRA", cliente_id=99999)))[0] == 404
    for mudanca in [
        {"numero": " "}, {"seguradora": " "}, {"ramo": " "}, {"cliente_id": 0},
        {"fim_vigencia": "2026-11-06"}, {"fim_vigencia": "2026-11-07"},
        {"inicio_vigencia": "2026-02-30"}, {"premio": "-0.01"}, {"premio": "10.001"},
        {"premio": "NaN"}, {"premio": "Infinity"}, {"premio": "abc"},
        {"premio": "10000000000.00"}, {"premio": None}, {"cliente_id": None},
        {"campo_desconhecido": True},
    ]:
        assert (await request("POST", "/apolices", {**payload, "numero": "INVALIDA", **mudanca}))[0] == 422

    segunda = dict(payload, numero="AP-2026-0002", cliente_id=2, premio="0.10")
    code, resposta2 = await request("POST", "/apolices", segunda)
    assert code == 201 and resposta2["premio"] == "0.10" and resposta2["id"] == 2
    code, resposta3 = await request("POST", "/apolices", dict(payload, numero="AP-2026-0003", premio="0.00"))
    assert code == 201 and resposta3["premio"] == "0.00"
    assert await request("GET", "/apolices", query="cliente_id=2") == (200, [resposta2])
    assert await request("GET", "/apolices", query="cliente_id=99999") == (200, [])
    assert await request("GET", "/apolices", query="offset=1&limite=1") == (200, [resposta2])
    assert (await request("GET", "/apolices", query="cliente_id=0"))[0] == 422
    assert (await request("GET", "/apolices", query="limite=0"))[0] == 422
    assert (await request("GET", "/apolices/99999"))[0] == 404
    assert (await request("GET", "/apolices/0"))[0] == 422
    assert await request("GET", "/clientes/1") == cliente_antes
    with TestSession() as db:
        assert db.get(Apolice, 1).premio_centavos == 125050
        assert db.get(Apolice, 2).premio_centavos == 10
        # A integridade do vínculo também é exigida pelo banco, fora da API.
        db.add(Apolice(numero="ORFA", cliente_id=99999, seguradora="Exemplo", ramo="Vida",
                       inicio_vigencia=date(2026, 11, 7), fim_vigencia=date(2027, 11, 7), premio_centavos=1))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("O banco aceitou uma apólice sem cliente existente.")
        assert len(db.scalars(select(Apolice)).all()) == 3


async def testar_alteracao_cancelamento():
    original = (await request("GET", "/apolices/1"))[1]
    for payload in [{}, {"premio": None}, {"premio": "-1"}, {"id": 2},
                    {"fim_vigencia": "2026-01-01"}, {"inicio_vigencia": "2028-01-01"}]:
        assert (await request("PATCH", "/apolices/1", payload))[0] == 422
        assert (await request("GET", "/apolices/1"))[1] == original
    assert (await request("PATCH", "/apolices/1", {"cliente_id": 99999}))[0] == 404
    assert (await request("PATCH", "/apolices/99999", {"premio": "10.00"}))[0] == 404
    assert (await request("PATCH", "/apolices/1", {"numero": "AP-2026-0002", "premio": "1.00"}))[0] == 409
    assert (await request("GET", "/apolices/1"))[1] == original
    code, alterada = await request("PATCH", "/apolices/1", {"premio": "1500.25", "numero": " novo-001 "})
    assert code == 200 and alterada == dict(original, premio="1500.25", numero="NOVO-001")
    code, _ = await request("PATCH", "/apolices/1", {"inicio_vigencia": "2028-01-01", "fim_vigencia": "2029-01-01"})
    assert code == 200
    for payload in [{}, {"motivo": " "}, {"motivo": None}, {"motivo": "x" * 501}]:
        assert (await request("POST", "/apolices/1/cancelamento", payload))[0] == 422
    assert (await request("POST", "/apolices/99999/cancelamento", {"motivo": "Solicitado pelo cliente"}))[0] == 404
    code, cancelada = await request("POST", "/apolices/1/cancelamento", {"motivo": " Solicitado pelo cliente "})
    assert code == 200 and cancelada["cancelada"] is True
    assert cancelada["cancelamento"]["motivo"] == "Solicitado pelo cliente"
    assert cancelada["cancelamento"]["registrado_em"]
    assert await request("GET", "/apolices/1") == (200, cancelada)
    assert cancelada in (await request("GET", "/apolices"))[1]
    assert (await request("POST", "/apolices/1/cancelamento", {"motivo": "Outra tentativa"}))[0] == 409
    assert (await request("PATCH", "/apolices/1", {"premio": "1.00"}))[0] == 409
    assert await request("GET", "/apolices/1") == (200, cancelada)
    assert (await request("GET", "/apolices/2"))[1]["cancelada"] is False


async def testar_vencimentos():
    hoje = date(2035, 5, 10)
    app.dependency_overrides[data_referencia] = lambda: hoje
    try:
        code, cliente = await request("POST", "/clientes", {"nome": "Cliente Vencimentos", "email": "vencimentos@example.com"})
        assert code == 201
        cliente_id = cliente["id"]
        registros = []
        # Fora da janela, limites inclusivos e empate com ordenação por ID.
        for i, dias in enumerate([-1, 0, 30, 31, 0, -2, 1]):
            payload = {"numero": f"VENC-{i}", "cliente_id": cliente_id,
                       "seguradora": "Exemplo", "ramo": "Vida", "premio": "10.00",
                       "inicio_vigencia": (hoje - timedelta(days=365)).isoformat(),
                       "fim_vigencia": (hoje + timedelta(days=dias)).isoformat()}
            code, registro = await request("POST", "/apolices", payload)
            assert code == 201
            registros.append(registro)
        for i in [5, 6]:
            assert (await request("POST", f"/apolices/{registros[i]['id']}/cancelamento", {"motivo": "Teste de exclusão"}))[0] == 200
        filtro = f"cliente_id={cliente_id}"
        assert await request("GET", "/apolices/vencidas", query=filtro) == (200, [registros[0]])
        assert await request("GET", "/apolices/a-vencer", query=filtro) == (200, [registros[1], registros[4], registros[2]])
        assert await request("GET", "/apolices/a-vencer", query=filtro + "&dias=0") == (200, [registros[1], registros[4]])
        assert await request("GET", "/apolices/a-vencer", query=filtro + "&dias=31") == (200, [registros[1], registros[4], registros[2], registros[3]])
        assert await request("GET", "/apolices/a-vencer", query=filtro + "&offset=1&limite=1") == (200, [registros[4]])
        for rota in ["/apolices/vencidas", "/apolices/a-vencer"]:
            assert await request("GET", rota, query="cliente_id=99999") == (200, [])
            for query in ["cliente_id=0", "offset=-1", "limite=0", "limite=101"]:
                assert (await request("GET", rota, query=query))[0] == 422
        for query in ["dias=-1", "dias=366", "dias=abc"]:
            assert (await request("GET", "/apolices/a-vencer", query=query))[0] == 422
        # Consultar vencimentos não remove nem modifica a apólice cancelada.
        assert (await request("GET", f"/apolices/{registros[5]['id']}"))[1]["cancelada"] is True
        print("PASS: vencimentos, datas-limite, canceladas, filtros, ordenação e paginação.")
    finally:
        app.dependency_overrides.pop(data_referencia, None)


async def testar_renovacao():
    original = (await request("GET", "/apolices/2"))[1]
    payload = {"numero": " RENOVADA-001 ", "inicio_vigencia": "2027-11-07",
               "fim_vigencia": "2028-11-07", "premio": "2000.15"}
    for alteracao in [{"inicio_vigencia": "2027-11-06"}, {"fim_vigencia": "2027-11-07"},
                      {"premio": "-1"}, {"premio": "1.001"}, {"numero": " "}, {"cliente_id": 1}]:
        assert (await request("POST", "/apolices/2/renovacao", {**payload, **alteracao}))[0] == 422
    assert (await request("POST", "/apolices/99999/renovacao", payload))[0] == 404
    assert (await request("POST", "/apolices/1/renovacao", payload))[0] == 409
    antes = (await request("GET", "/apolices"))[1]
    assert (await request("POST", "/apolices/2/renovacao", dict(payload, numero="AP-2026-0003")))[0] == 409
    assert (await request("GET", "/apolices"))[1] == antes
    code, nova = await request("POST", "/apolices/2/renovacao", payload)
    assert code == 201 and nova["anterior_id"] == 2 and nova["renovada_por_id"] is None
    assert nova["cliente_id"] == original["cliente_id"] and nova["seguradora"] == original["seguradora"]
    assert nova["ramo"] == original["ramo"] and nova["premio"] == "2000.15" and nova["numero"] == "RENOVADA-001"
    assert (await request("GET", "/apolices/2"))[1] == dict(original, renovada_por_id=nova["id"])
    assert (await request("POST", "/apolices/2/renovacao", dict(payload, numero="OUTRA-RENOVACAO")))[0] == 409
    for apolice_id in [2, nova["id"]]:
        assert (await request("PATCH", f"/apolices/{apolice_id}", {"premio": "1.00"}))[0] == 409
    assert (await request("POST", "/apolices/2/cancelamento", {"motivo": "Teste"}))[0] == 409
    app.dependency_overrides[data_referencia] = lambda: date(2027, 11, 7)
    try:
        for rota in ["vencidas", "a-vencer"]:
            assert 2 not in [a["id"] for a in (await request("GET", f"/apolices/{rota}"))[1]]
    finally:
        app.dependency_overrides.pop(data_referencia, None)
    # Permite encadear uma segunda renovação, mantendo o histórico de três períodos.
    code, terceira = await request("POST", f"/apolices/{nova['id']}/renovacao",
        dict(payload, numero="RENOVADA-002", inicio_vigencia="2028-11-07", fim_vigencia="2029-11-07"))
    assert code == 201 and terceira["anterior_id"] == nova["id"]
    assert (await request("POST", f"/apolices/{terceira['id']}/cancelamento", {"motivo": "Solicitado pelo cliente"}))[0] == 200
    print("PASS: renovação, histórico, transação, datas, duplicatas e cadeia de renovações.")


async def testar_buscas():
    async def buscar(rota, **params):
        code, dados = await request("GET", rota, query=urlencode(params))
        assert code == 200
        return dados

    clientes = (await request("GET", "/clientes"))[1]
    assert [c["id"] for c in await buscar("/clientes", nome=" aNA ", ativo="true")] == [1]
    assert await buscar("/clientes", nome="inexistente") == []
    assert (await request("PATCH", "/clientes/2", {"ativo": False}))[0] == 200
    assert [c["id"] for c in await buscar("/clientes", ativo="false")] == [2]
    assert await buscar("/clientes", nome="Ana", ativo="false") == []
    assert [c["id"] for c in await buscar("/clientes", ativo="true", offset=1, limite=1)] == [clientes[2]["id"]]
    # Percentual e sublinhado são texto literal, não curingas do SQL LIKE.
    assert await buscar("/clientes", nome="%") == []
    apolices = (await request("GET", "/apolices"))[1]
    assert await buscar("/apolices", numero="renovada-001") == [a for a in apolices if a["numero"] == "RENOVADA-001"]
    assert await buscar("/apolices", seguradora="exemplo", ramo="vida", cliente_id=3) == [a for a in apolices if a["cliente_id"] == 3 and a["ramo"] == "Vida"]
    for campo in ["cancelada", "renovada"]:
        for valor in [True, False]:
            esperado = [a for a in apolices if (a["cancelada"] if campo == "cancelada" else a["renovada_por_id"] is not None) == valor]
            assert await buscar("/apolices", **{campo: str(valor).lower()}) == esperado
    assert await buscar("/apolices", cancelada="false", renovada="true", cliente_id=2) == [a for a in apolices if not a["cancelada"] and a["renovada_por_id"] is not None and a["cliente_id"] == 2]
    assert await buscar("/apolices", numero="_TESTE%") == []
    assert await buscar("/apolices", seguradora="inexistente") == []
    esperado = [a for a in apolices if not a["cancelada"]]
    assert await buscar("/apolices", cancelada="false", offset=1, limite=1) == esperado[1:2]
    for rota, params in [("/clientes", {"nome": " "}), ("/clientes", {"ativo": "talvez"}),
                         ("/apolices", {"numero": ""}), ("/apolices", {"seguradora": " "}),
                         ("/apolices", {"ramo": "x" * 61}), ("/apolices", {"cancelada": "talvez"}),
                         ("/apolices", {"renovada": "talvez"})]:
        assert (await request("GET", rota, query=urlencode(params)))[0] == 422
    print("PASS: buscas, filtros combinados, texto literal, validação e paginação.")


async def testar_telefone():
    clientes = []
    for i, telefone in enumerate(["(53) 99999-1234", "53999991234", "+55 (53) 99999-1234", None, "53999991235"]):
        code, cliente = await request("POST", "/clientes", {"nome": f"Contato Compartilhado {i}",
            "email": f"telefone{i}@example.com", "telefone": telefone})
        assert code == 201
        clientes.append(cliente)
    apolices = []
    for i, dono in enumerate([0, 0, 1, 2, 4]):
        code, apolice = await request("POST", "/apolices", {"numero": f"TEL-{i}",
            "cliente_id": clientes[dono]["id"], "seguradora": "Exemplo", "ramo": "Vida",
            "inicio_vigencia": "2026-01-01", "fim_vigencia": "2027-01-01", "premio": "50.00"})
        assert code == 201
        apolices.append(apolice)
    async def buscar(rota, **params):
        return await request("GET", rota, query=urlencode(params))
    for telefone in ["53999991234", "(53) 99999-1234", "53 99999.1234"]:
        assert await buscar("/clientes", telefone=telefone) == (200, clientes[:2])
        assert await buscar("/apolices", telefone=telefone) == (200, apolices[:3])
    assert await buscar("/clientes", telefone="+55 (53) 99999-1234") == (200, [clientes[2]])
    assert await buscar("/clientes", telefone="999991234") == (200, [])
    assert await buscar("/apolices", telefone="53999991234", cliente_id=clientes[1]["id"], ramo="vida") == (200, [apolices[2]])
    assert await buscar("/apolices", telefone="53999991234", offset=1, limite=1) == (200, [apolices[1]])
    assert (await request("PATCH", f"/clientes/{clientes[1]['id']}", {"ativo": False}))[0] == 200
    assert await buscar("/clientes", telefone="53999991234", ativo="true") == (200, [clientes[0]])
    assert await buscar("/clientes", telefone="00000000000") == (200, [])
    for telefone in ["", " ", "()-", "abc", "53%123", "1" * 26]:
        for rota in ["/clientes", "/apolices"]:
            assert (await buscar(rota, telefone=telefone))[0] == 422
    # A busca acompanha o cadastro atual; não duplica contato em cada apólice.
    assert (await request("PATCH", f"/clientes/{clientes[0]['id']}", {"telefone": "(53) 98888-0000"}))[0] == 200
    assert await buscar("/apolices", telefone="53988880000") == (200, apolices[:2])
    assert (await request("PATCH", f"/clientes/{clientes[0]['id']}", {"telefone": None}))[0] == 200
    assert await buscar("/apolices", telefone="53988880000") == (200, [])
    print("PASS: telefone formatado, contatos compartilhados, várias apólices, paginação e atualização do contato.")


async def testar_autenticacao():
    global TOKEN
    from pydantic import ValidationError
    senha = "Senha de teste 123!"
    with TestSession() as db:
        usuario = criar_usuario(db, UsuarioCriar(nome="Operador Teste", email="OPERADOR@example.com", senha=senha))
        usuario_id = usuario.id
        assert usuario.senha_hash.startswith("$argon2") and senha not in usuario.senha_hash
    # Todas as rotas de negócio exigem token, inclusive gravações.
    # FastAPI pode agrupar roteadores; OpenAPI enumera todas as operações públicas.
    for path, operacoes in app.openapi()["paths"].items():
        if path.startswith(("/clientes", "/apolices")):
            for method in operacoes:
                rota = path.replace("{cliente_id}", "1").replace("{apolice_id}", "1")
                assert (await request(method.upper(), rota, token=None))[0] == 401
    assert await request("GET", "/health", token=None) == (200, {"status": "ok"})
    erros = []
    for email, password in [("operador@example.com", "Errada"), ("ausente@example.com", senha)]:
        code, data = await request("POST", "/auth/login", {"email": email, "senha": password}, token=None)
        assert code == 401
        erros.append(data)
    assert erros[0] == erros[1]
    code, erro = await request("POST", "/auth/login", {"email": "inválido", "senha": senha}, token=None)
    assert code == 422 and senha not in json.dumps(erro)
    code, erro = await request("POST", "/auth/login", {"email": "operador@example.com", "senha": "s" * 129}, token=None)
    assert code == 422 and "s" * 129 not in json.dumps(erro)
    try:
        UsuarioCriar(nome="Teste", email="teste@example.com", senha="curta")
    except ValidationError:
        pass
    else:
        raise AssertionError("Senha curta foi aceita na criação.")
    login = {"email": "OPERADOR@example.com", "senha": senha}
    code, data = await request("POST", "/auth/login", login, token=None)
    assert code == 200 and data["token_type"] == "bearer" and data["expires_in"] == 1800
    primeiro = data["access_token"]
    code, perfil = await request("GET", "/auth/me", token=primeiro)
    assert code == 200 and perfil == {"id": usuario_id, "nome": "Operador Teste", "email": "operador@example.com", "ativo": True}
    assert (await request("GET", "/clientes", token="x" * 43))[0] == 401
    assert (await request("GET", "/auth/me", token=primeiro + "alterado"))[0] == 401
    with TestSession() as db:
        sessao = db.get(SessaoUsuario, resumo_token(primeiro))
        assert sessao is not None and sessao.token_hash != primeiro
        sessao.expira_em = agora_utc() - timedelta(seconds=1)
        db.commit()
    assert (await request("GET", "/clientes", token=primeiro))[0] == 401
    segundo = (await request("POST", "/auth/login", login, token=None))[1]["access_token"]
    assert segundo != primeiro
    # O helper de requisições espera JSON; logout 204 não tem corpo.
    assert await request("POST", "/auth/logout", token=segundo) == (204, None)
    assert (await request("GET", "/clientes", token=segundo))[0] == 401
    terceiro = (await request("POST", "/auth/login", login, token=None))[1]["access_token"]
    with TestSession() as db:
        usuario = db.get(Usuario, usuario_id)
        usuario.ativo = False
        db.commit()
    assert (await request("GET", "/clientes", token=terceiro))[0] == 401
    assert (await request("POST", "/auth/login", login, token=None))[0] == 401
    with TestSession() as db:
        usuario = db.get(Usuario, usuario_id)
        usuario.ativo = True
        db.commit()
    TOKEN = (await request("POST", "/auth/login", login, token=None))[1]["access_token"]
    print("PASS: autenticação, hash Argon2, proteção de rotas, expiração, logout e usuário inativo.")


async def main():
    await testar_autenticacao()
    assert await request("GET", "/health") == (200, {"status": "ok"})
    assert await request("GET", "/clientes") == (200, [])
    code, cliente = await request("POST", "/clientes", {"nome": " Ana Exemplo ", "email": "ANA@example.com", "telefone": "53999999999"})
    assert code == 201 and cliente == {"id": 1, "nome": "Ana Exemplo", "email": "ana@example.com", "telefone": "53999999999", "ativo": True}
    assert await request("GET", "/clientes/1") == (200, cliente)
    code, _ = await request("POST", "/clientes", {"nome": "Outra Pessoa", "email": "ana@example.com"})
    assert code == 409
    for payload in [
        {"nome": "  ", "email": "ok@example.com"},
        {"nome": "Ana Exemplo", "email": "email-invalido"},
        {"nome": "Ana Exemplo"},
        {"nome": "Ana Exemplo", "email": "ok@example.com", "id": 99},
    ]:
        assert (await request("POST", "/clientes", payload))[0] == 422
    code, segundo = await request("POST", "/clientes", {"nome": "Bruno Exemplo", "email": "bruno@example.com", "telefone": " "})
    assert code == 201 and segundo["telefone"] is None
    assert await request("GET", "/clientes", query="offset=1&limite=1") == (200, [segundo])
    assert (await request("GET", "/clientes", query="limite=0"))[0] == 422
    assert (await request("GET", "/clientes/99999"))[0] == 404
    assert (await request("GET", "/clientes/0"))[0] == 422
    assert len((await request("GET", "/clientes"))[1]) == 2
    atualizado = dict(cliente, telefone="53988888888")
    assert await request("PATCH", "/clientes/1", {"telefone": "53988888888"}) == (200, atualizado)
    assert await request("GET", "/clientes/1") == (200, atualizado)
    atualizado["ativo"] = False
    assert await request("PATCH", "/clientes/1", {"ativo": False}) == (200, atualizado)
    assert await request("GET", "/clientes/1") == (200, atualizado)
    atualizado["ativo"] = True
    assert await request("PATCH", "/clientes/1", {"ativo": True}) == (200, atualizado)
    atualizado["telefone"] = None
    assert await request("PATCH", "/clientes/1", {"telefone": None}) == (200, atualizado)

    for payload in [{}, {"nome": None}, {"email": None}, {"ativo": None},
                    {"nome": " "}, {"email": "invalido"}, {"id": 99},
                    {"telefone": "9" * 26}]:
        assert (await request("PATCH", "/clientes/1", payload))[0] == 422
        assert await request("GET", "/clientes/1") == (200, atualizado)

    assert (await request("PATCH", "/clientes/1", {"email": "BRUNO@example.com", "nome": "Não deve ser salvo"}))[0] == 409
    assert await request("GET", "/clientes/1") == (200, atualizado)
    assert await request("GET", "/clientes/2") == (200, segundo)
    assert (await request("PATCH", "/clientes/99999", {"ativo": False}))[0] == 404
    assert (await request("PATCH", "/clientes/0", {"ativo": False}))[0] == 422

    atualizado.update(nome="Ana Atualizada", email="ana.nova@example.com")
    assert await request("PATCH", "/clientes/1", {"nome": " Ana Atualizada ", "email": "ANA.NOVA@example.com"}) == (200, atualizado)
    assert await request("PATCH", "/clientes/1", {"telefone": " "}) == (200, atualizado)
    assert len((await request("GET", "/clientes"))[1]) == 2
    await testar_apolices()
    await testar_alteracao_cancelamento()
    await testar_vencimentos()
    await testar_renovacao()
    await testar_buscas()
    await testar_telefone()
    print("PASS: clientes e PATCH; cadastro/consultas de apólices, vínculo, duplicatas, datas, valores exatos, filtros e paginação. Banco em memória.")


app.dependency_overrides[get_db] = test_db
try:
    asyncio.run(main())
finally:
    app.dependency_overrides.pop(get_db, None)
    test_engine.dispose()
