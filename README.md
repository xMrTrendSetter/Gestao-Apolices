# Gestão de Apólices

API REST para organizar clientes e apólices de uma corretora de seguros.
Projeto de portfólio com foco em desenvolvimento backend: persistência relacional,
validação de dados, regras de negócio, autenticação e testes de integração.

## Funcionalidades

- Cadastro, consulta, atualização e inativação de clientes.
- Cadastro de apólices vinculadas ao cliente e valores monetários exatos.
- Cancelamento com motivo e data, preservando o registro.
- Renovação que cria uma sucessora e mantém o vínculo com a anterior.
- Consulta de vencidas e a vencer, com janela configurável de até 365 dias.
- Busca por nome, número, seguradora, ramo e telefone, com filtros e paginação.
- Login com senha protegida por Argon2, tokens Bearer de 30 minutos e logout.

## Tecnologias

| Ferramenta | Uso |
| --- | --- |
| Python | Linguagem do backend; desenvolvimento e testes com 3.14 |
| FastAPI e Uvicorn | API HTTP, validação das requisições e servidor ASGI |
| SQLAlchemy | Modelos relacionais, consultas e transações |
| SQLite | Persistência local com chaves estrangeiras habilitadas |
| Pydantic | Schemas, validação e serialização |
| pwdlib e Argon2 | Hash e verificação de senhas |
| OpenAPI / Swagger UI | Documentação interativa gerada pela API |
| Insomnia | Verificação manual das requisições |

## Executar localmente

Os comandos abaixo são para PowerShell no Windows, dentro da pasta do projeto.
Use Python 3.14, versão em que o projeto foi validado.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.criar_usuario
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

O comando de criação de usuário pede nome, e-mail e senha de 12 a 128 caracteres.
A senha não aparece durante a digitação. Não há credenciais padrão.
O banco local é criado automaticamente e não faz parte do repositório.

- API: http://127.0.0.1:8000
- Documentação interativa: http://127.0.0.1:8000/docs
- Especificação OpenAPI: http://127.0.0.1:8000/openapi.json

### Autenticar no Insomnia

Crie uma requisição POST para `/auth/login`, com **No Auth** e Body **JSON**:

```json
{
  "email": "seu-email@example.com",
  "senha": "a senha escolhida no terminal"
}
```

Copie o `access_token` da resposta e configure **Auth → Bearer Token** nas pastas
Clientes e Apólices. Nas requisições, selecione **Inherit from parent**. Login e
health permanecem sem autenticação. O `/docs` aceita o token em **Authorize**.

Consulte o [guia da API e do Insomnia](docs/GUIA_API.md) para exemplos completos,
filtros, validações, renovação e configuração do token.

## Rotas principais

| Método | Rota | Finalidade |
| --- | --- | --- |
| GET | `/health` | Verificar disponibilidade |
| POST | `/auth/login` | Obter token de acesso |
| GET | `/auth/me` | Consultar usuário autenticado |
| POST | `/auth/logout` | Revogar a sessão atual |
| POST / GET | `/clientes` | Cadastrar e listar clientes |
| GET / PATCH | `/clientes/{id}` | Consultar e atualizar cliente |
| POST / GET | `/apolices` | Cadastrar e listar apólices |
| GET / PATCH | `/apolices/{id}` | Consultar e atualizar apólice |
| POST | `/apolices/{id}/cancelamento` | Registrar cancelamento |
| POST | `/apolices/{id}/renovacao` | Criar apólice sucessora |
| GET | `/apolices/vencidas` | Listar vencidas sem sucessora |
| GET | `/apolices/a-vencer` | Listar próximos vencimentos sem sucessora |

As rotas de negócio e de perfil exigem Bearer. Não há exclusão física de clientes
ou apólices. As listas aceitam `offset` e `limite` (padrão 50, máximo 100).

## Regras e decisões técnicas

- Prêmios são recebidos como texto decimal e armazenados em centavos inteiros,
  evitando aproximação de ponto flutuante no SQLite.
- E-mails e números de apólice são únicos e normalizados; telefone não é único,
  pois diferentes clientes podem compartilhar um contato.
- Busca por telefone compara o número completo, ignorando a formatação. Não
  acrescenta DDD ou DDI. O contato é consultado no cliente, sem duplicá-lo nas apólices.
- Renovação grava a nova apólice e o vínculo em uma única transação. A vigência
  começa no fim da anterior ou depois; intervalos sem cobertura são permitidos.
- Apólices vinculadas a renovações ficam bloqueadas para edição nesta etapa.
  Canceladas e apólices com sucessora ficam fora das consultas de vencimentos.
- Vencimentos usam a data civil de Brasília (UTC-3), incluindo hoje em a-vencer.
- Senhas usam Argon2. Tokens são aleatórios e opacos, com apenas seu hash SHA-256
  e expiração em UTC armazenados no banco. Logout revoga a sessão imediatamente.

## Estrutura

```text
app/
  main.py             # Inicialização e registro dos roteadores
  database.py         # Engine, sessões e base dos modelos
  models.py           # Tabelas e vínculos relacionais
  schemas.py          # Entrada, saída e validação
  dependencies.py     # Dependências compartilhadas
  search.py           # Filtros de texto e telefone
  security.py         # Senhas e sessões de autenticação
  criar_usuario.py    # Cadastro de operadores pelo terminal
  routers/
    auth.py
    clientes.py
    apolices.py
tests/
  smoke.py            # Testes de integração com SQLite em memória
docs/
  GUIA_API.md         # Exemplos para testar a API
```

## Testes

```powershell
.\.venv\Scripts\python.exe -B tests/smoke.py
```

Os testes executam requisições pela interface ASGI com banco SQLite em memória,
sem modificar dados locais. Cobrem autenticação e revogação, cadastro, consultas,
validações, atualização parcial, duplicatas, integridade referencial, cancelamento,
renovação, limites de datas, valores monetários, filtros e paginação.
O mesmo comando é executado pelo GitHub Actions em Python 3.14.

## Escopo e próximas melhorias

O projeto é uma API de estudo para uma única corretora: operadores autorizados
compartilham o cadastro. Ainda não inclui perfis de acesso, migrações versionadas,
auditoria de cada edição, recuperação de senha ou limitação de tentativas de login.
Buscas textuais no SQLite ignoram caixa para ASCII, mas não removem acentos.
As datas de cobertura não incluem horários. Uma publicação requer HTTPS.

Utilize dados fictícios para demonstração. Banco local, ambiente virtual,
credenciais, caches e exportações locais do Insomnia são excluídos pelo `.gitignore`.
