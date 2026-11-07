# Guia da API e do Insomnia

API de estudo para gestão de clientes e apólices de seguros, desenvolvida em
Python com FastAPI, SQLAlchemy, SQLite e validação de dados com Pydantic.
Inclui cadastro e atualização de clientes, cancelamento e renovação de apólices,
consultas de vencimentos e buscas por dados do cadastro e telefone.

## Executar no PowerShell

Requer Python 3.11 ou superior. Testado com Python 3.14.
Na pasta `Gestao-Apolices`, prepare o ambiente (somente na primeira execução):

```powershell
py -m venv .venv
```

Instale as dependências e inicie:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

O banco `gestao_apolices.db` e as tabelas de clientes e apólices são criados automaticamente
quando o servidor inicia. Os dados ficam salvos entre reinicializações.

## Autenticação e configuração no Insomnia

As rotas `/clientes` e `/apolices`, incluindo buscas, vencimentos, renovação e
cancelamento, exigem um token. `/health` e `/auth/login` são públicos.
Clientes segurados e usuários que operam a API são cadastros diferentes.

### 1. Criar seu usuário pelo PowerShell

Na pasta `Gestao-Apolices`, execute (pode ser em outro terminal):

```powershell
.\.venv\Scripts\python.exe -m app.criar_usuario
```

Informe nome, e-mail, senha de 12 a 128 caracteres e confirmação. A senha não
aparece durante a digitação. Não há senha padrão nem cadastro público de usuários.
O comando adiciona as tabelas necessárias sem apagar clientes ou apólices.

### 2. Fazer login

Crie a pasta **Autenticação** no Insomnia e a requisição **Login**:
POST `http://127.0.0.1:8000/auth/login`, Auth **No Auth**, Body **JSON**:

```json
{
  "email": "seu-email@example.com",
  "senha": "a senha que você escolheu"
}
```

Use suas credenciais cadastradas. Retorna 200 com `access_token`, `token_type`
igual a `bearer` e `expires_in` igual a 1800 segundos (30 minutos).

### 3. Acessar as rotas protegidas

Na requisição de clientes ou apólices, abra **Auth → Bearer Token** e cole somente
o valor de `access_token`, sem aspas e sem escrever `Bearer` no campo Token.
Também pode configurar Bearer na pasta e selecionar **Inherit from parent** nas
requisições filhas. O cabeçalho enviado será `Authorization: Bearer <token>`.
No `/docs`, use Authorize e informe o mesmo token.

GET `/auth/me` com Bearer retorna o perfil, sem hash nem senha.
POST `/auth/logout` com Bearer e sem Body retorna **204**, sem conteúdo, revogando
imediatamente aquele token. Outros logins do mesmo usuário continuam válidos.
Token ausente, inválido, expirado ou revogado retorna **401**, assim como usuário
inativo. Faça login novamente quando expirar. Login errado tem mensagem genérica.

### Implementação e limites

As senhas usam Argon2 via pwdlib; senhas não são armazenadas em texto puro.
Os tokens são aleatórios e opacos, com apenas SHA-256 do token salvo no SQLite,
data de expiração em UTC e vínculo ao usuário. Eles persistem entre reinícios até
expirar ou fazer logout. Não são JWT e não exigem chave secreta em arquivo.
Não há refresh token, recuperação de senha, perfis ou limitação automática de
tentativas de login nesta etapa. Em uma publicação, use HTTPS para transportar
credenciais e tokens. Não versione credenciais nem exportações do Insomnia com tokens.

## Testar no Insomnia

| Método | URL | Finalidade |
| --- | --- | --- |
| GET | http://127.0.0.1:8000/health | Verificar o servidor |
| POST | http://127.0.0.1:8000/clientes | Cadastrar cliente |
| GET | http://127.0.0.1:8000/clientes | Listar clientes |
| GET | http://127.0.0.1:8000/clientes/1 | Consultar cliente pelo ID |
| PATCH | http://127.0.0.1:8000/clientes/1 | Atualizar, inativar ou reativar cliente |
| POST | http://127.0.0.1:8000/apolices | Cadastrar apólice vinculada a um cliente |
| GET | http://127.0.0.1:8000/apolices | Listar apólices |
| GET | http://127.0.0.1:8000/apolices/1 | Consultar apólice pelo ID |
| PATCH | http://127.0.0.1:8000/apolices/1 | Atualizar apólice |
| POST | http://127.0.0.1:8000/apolices/1/cancelamento | Cancelar com motivo |
| POST | http://127.0.0.1:8000/apolices/1/renovacao | Renovar preservando a anterior |
| GET | http://127.0.0.1:8000/apolices/vencidas | Consultar vencidas |
| GET | http://127.0.0.1:8000/apolices/a-vencer | Consultar próximos vencimentos |

No POST, selecione **Body → JSON** e use dados fictícios:

```json
{
  "nome": "Ana Exemplo",
  "email": "ana@example.com",
  "telefone": "53999999999"
}
```

A resposta de sucesso é **201 Created**, com os campos `id`, `nome`, `email`,
`telefone` e `ativo`. O telefone é opcional; `ativo` começa como `true`.

E-mail repetido retorna **409 Conflict**; dados inválidos retornam **422**;
consulta de ID inexistente retorna **404**. Os e-mails são normalizados para
minúsculas. A validação verifica o formato, sem confirmar a existência da caixa.

A listagem aceita `?offset=0&limite=50`, com limite máximo de 100 registros.
A documentação interativa também fica em http://127.0.0.1:8000/docs.

## Atualizar clientes no Insomnia

Crie uma requisição **PATCH** para `http://127.0.0.1:8000/clientes/1`.
Selecione **Body → JSON** e envie somente o que deseja mudar:

```json
{
  "telefone": "53988888888"
}
```

Para inativar, envie `{"ativo": false}`; para reativar, `{"ativo": true}`.
Para remover o telefone, envie `{"telefone": null}`.

Campos omitidos mantêm seus valores; `nome`, `email` e `ativo` não aceitam `null`.
O corpo vazio `{}` retorna 422. E-mail de outro cliente retorna 409 e nenhuma
alteração da requisição é salva. Cliente inexistente retorna 404. No sucesso,
a resposta é **200 OK**, com o cadastro completo atualizado.

O cliente inativado continua no banco e nas consultas, preservando o histórico.

## Apólices no Insomnia

Crie uma pasta **Apólices** e uma requisição **POST** para
`http://127.0.0.1:8000/apolices`. Em **Body → JSON**, envie:

```json
{
  "numero": "AP-2026-0001",
  "cliente_id": 1,
  "seguradora": "Seguradora Exemplo",
  "ramo": "Automóvel",
  "inicio_vigencia": "2026-11-07",
  "fim_vigencia": "2027-11-07",
  "premio": "1250.50"
}
```

Use o ID de um cliente existente. O sucesso retorna **201 Created**, incluindo
o ID da apólice. A consulta desse registro é `GET /apolices/1`.

Regras implementadas:

- Número obrigatório e único, normalizado para maiúsculas.
- Cliente inexistente retorna **404**.
- Número repetido retorna **409**.
- Datas no formato `AAAA-MM-DD`; fim estritamente posterior ao início.
- Prêmio não negativo, com no máximo duas casas decimais e dez dígitos inteiros.
- Datas, campos e valores inválidos retornam **422**.

Envie `premio` como texto decimal com ponto, como `"1250.50"`. A API usa `Decimal`
e devolve o valor como texto para manter a precisão. No SQLite, o valor é guardado
como centavos inteiros, evitando aproximações de ponto flutuante.

Para listar as apólices de um cliente, use `GET /apolices?cliente_id=1`.
A listagem também aceita `offset` e `limite`, com limite máximo de 100.
As apólices não alteram os dados nem o status do cliente vinculado.

## Arquivos

- `app/database.py`: banco, sessões e classe-base dos modelos.
- `app/models.py`: tabelas de clientes e apólices, com vínculo por chave estrangeira.
- `app/schemas.py`: validação de entrada e formato de resposta.
- `app/main.py`: inicialização e registro dos roteadores.
- `app/routers/clientes.py`: rotas de cadastro, consulta, atualização e busca de clientes.
- `app/routers/apolices.py`: rotas de apólices, vencimentos, cancelamento e renovação.
- `app/dependencies.py`: sessão de banco e data de referência compartilhadas.
- `app/search.py`: filtros compartilhados de texto e telefone.
- `tests/smoke.py`: testes HTTP com SQLite isolado em memória.
- `app/security.py`: hashes de senha, emissão e validação de sessões.
- `app/routers/auth.py`: login, perfil e logout.
- `app/criar_usuario.py`: criação de usuários autorizados pelo terminal.

## Verificações

```powershell
.\.venv\Scripts\python.exe -B tests/smoke.py
```

O teste usa banco em memória e não altera os cadastros feitos pelo Insomnia.
As rotas de clientes e apólices exigem autenticação Bearer. Veja a seção de autenticação.


## Atualizar e cancelar apólices

PATCH `/apolices/1`, Body JSON: `{"premio": "1500.25"}`. Retorna 200.
Campos omitidos são preservados. Corpo vazio, campos desconhecidos, null e
vigência inválida retornam 422; número duplicado retorna 409; ID inexistente, 404.

POST `/apolices/1/cancelamento`, Body JSON:
`{"motivo": "Cancelamento solicitado pelo cliente"}`. Retorna 200.
O motivo deve ter de 3 a 500 caracteres. A resposta inclui `cancelada` e
`cancelamento` (motivo e registrado_em em UTC). Repetir o cancelamento ou editar
uma apólice cancelada retorna 409. Não há reativação nesta etapa.

Os cancelamentos ficam em uma tabela própria, criada na inicialização, sem
alterar as tabelas existentes. Apólices canceladas continuam nas consultas e
seus números não são liberados para reutilização. Não há exclusão física nem
versionamento das edições nesta etapa.


## Consultar vencimentos no Insomnia

Crie requisições GET, sem Body e com Bearer Token:

- `http://127.0.0.1:8000/apolices/vencidas`: fim da vigência anterior a hoje.
- `http://127.0.0.1:8000/apolices/a-vencer`: entre hoje e hoje + 30 dias, inclusive.
- `http://127.0.0.1:8000/apolices/a-vencer?dias=7`: personalizar a janela.

A referência é a data civil de Brasília (UTC-3). Uma apólice que termina hoje
entra em a-vencer, não em vencidas. `dias=0` consulta somente hoje; máximo 365.
As duas rotas excluem canceladas e apólices que já possuem sucessora, e aceitam `cliente_id`, `offset` e `limite`
(padrão 50, máximo 100). Ordenação por fim da vigência crescente e ID.
Retornam 200 com uma lista; `[]` indica ausência de resultados.
Não enviam notificações nem alteram as apólices.


## Renovação de apólices

POST `http://127.0.0.1:8000/apolices/2/renovacao`, Body JSON:

```json
{
  "numero": "AP-2027-0001",
  "inicio_vigencia": "2027-11-07",
  "fim_vigencia": "2028-11-07",
  "premio": "1500.00"
}
```

Use o ID de uma apólice não cancelada e ainda não renovada. A data inicial deve
ser igual ou posterior ao fim da anterior; intervalos sem cobertura são permitidos.
O mesmo dia é aceito porque esta API trabalha com datas, sem horários de cobertura.
Cliente, seguradora e ramo são copiados da anterior. Número novo é obrigatório.
Retorna 201 com a nova apólice e `anterior_id`; a antiga passa a informar
`renovada_por_id`, mantendo os demais dados. É possível renovar a sucessora depois.

Canceladas, já renovadas e números repetidos retornam 409; datas/valores inválidos,
422; apólice inexistente, 404. A gravação é atômica e os vínculos são únicos no banco.
Uma tabela de vínculos é criada na inicialização, preservando os registros existentes.
Apólices com sucessora saem das consultas de vencimentos, mas permanecem na listagem
geral. Nesta etapa, registros vinculados a renovações ficam bloqueados para edição;
uma apólice com sucessora não pode ser cancelada, mas a última da cadeia pode.


## Buscas e filtros nas listagens

Exemplos GET no Insomnia, sem Body:

- `/clientes?nome=Ana`: nome contém o texto informado.
- `/clientes?ativo=true`: somente ativos; `false` para inativos.
- `/clientes?nome=Ana&ativo=true`: combinar filtros.
- `/apolices?numero=AP-2026`: parte do número.
- `/apolices?seguradora=Exemplo&ramo=Vida`: seguradora e ramo.
- `/apolices?cancelada=true`: somente canceladas; `false` para não canceladas.
- `/apolices?renovada=true`: apólices que possuem sucessora; `false` para as que não possuem.
- `/apolices?cliente_id=1&cancelada=false&renovada=false`: combinar condições.

Filtros omitidos não restringem resultados. Todas as condições são combinadas com
AND e aplicadas antes de `offset` e `limite`. Ordenação crescente por ID.
As buscas são parciais, removem espaços nas pontas e tratam `%` e `_` como texto
literal. Texto vazio ou apenas espaços retorna 422. No SQLite, a comparação sem
distinção de maiúsculas é garantida para caracteres ASCII; acentos devem manter a
grafia e caixa correspondentes. Não há remoção automática de acentos.
`renovada` indica que a apólice originou uma sucessora, não apenas que veio de uma
renovação. Ausência de resultados retorna 200 com `[]`.


## Busca por telefone

- GET `/clientes?telefone=53999991234`: todos os clientes com esse número.
- GET `/apolices?telefone=53999991234`: todas as apólices vinculadas a esses clientes.
- GET `/apolices?telefone=53999991234&cancelada=false`: combinar com outros filtros.

A comparação usa o número completo, ignorando espaços, parênteses, traços, pontos
e o sinal `+`. Funciona também com contatos já cadastrados com formatação, sem
reescrever os dados. O telefone não é único: clientes diferentes podem compartilhá-lo.
Não se acrescenta nem remove DDI/DDD: `+55 (53) 99999-1234` corresponde a
`5553999991234`, mas não a `53999991234`. Não é uma busca parcial.
No Insomnia, prefira informar o telefone na aba Params, que codifica caracteres
como `+` corretamente; alternativamente use somente dígitos na URL.

O formato salvo e exibido permanece igual. O contato fica no cliente e as apólices
usam seu vínculo; alterar ou remover o telefone muda as buscas seguintes.
Parâmetros vazios, sem dígitos, com letras ou com mais de 25 caracteres retornam 422.


## Escopo atual

Use dados fictícios no ambiente de estudo. A API exige autenticação nas rotas de negócio. Os usuários autorizados compartilham
o cadastro da corretora; ainda não há perfis ou permissões diferentes por usuário. Não há envio de mensagens,
reativação de cancelamentos, auditoria de cada edição ou versionamento do banco
com migrações. As datas de cobertura não incluem horários. O projeto usa centavos
inteiros para valores e vínculos entre períodos para o histórico de renovação.
