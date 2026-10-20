# Sistema de Gestão de Dietas Hospitalares

Plataforma multifilial para solicitação, preparo, entrega e auditoria de dietas hospitalares.

**Stack:** FastAPI (Python) · React + Vite · PostgreSQL 16 · WebSockets · Impressão ESC/POS · Docker

---

## Estrutura do projeto

Pasta única de desenvolvimento nesta estação: `C:\Users\Suporte\Documents\Projeto Cnutri`.
Ela contém o repositório `Markyto84/Cnutri`, com o histórico Git e as correções locais mais recentes.
Os caminhos anteriores do LM Studio e da cópia do Codex apontam para esta mesma pasta.

```
Projeto Cnutri/
├── backend/                  # API FastAPI (app/), Dockerfile
├── frontend/                 # SPA React (src/), Dockerfile + nginx.conf
├── configuracoes/            # Cópias versionadas dos esquemas de formulário
├── backups/                  # Backups locais do banco (fora do Git)
├── work/                     # Logs e processos locais (fora do Git)
├── docker-compose.yml        # Desenvolvimento (só o PostgreSQL)
├── docker-compose.prod.yml   # Produção (banco + backend + frontend)
├── start.ps1                 # Inicia o ambiente Windows
└── stop.ps1                  # Para os processos desta cópia
```

## Como rodar em um servidor Linux

### 1. Instalar o Docker (se ainda não tiver)

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
```

### 2. Copiar o projeto para o servidor

Por exemplo, com `scp` (a partir da máquina Windows):

```powershell
scp -r projeto-dietas-hospitalares usuario@IP-DO-SERVIDOR:/opt/
```

### 3. Criar o arquivo de variáveis (opcional, recomendado)

Na pasta do projeto no servidor, crie um `.env`:

```bash
cd /opt/projeto-dietas-hospitalares
cat > .env <<'EOF'
POSTGRES_PASSWORD=escolha-uma-senha-forte
JWT_SECRET=escolha-um-segredo-longo-e-aleatorio
EOF
chmod 600 .env
```

### 4. Subir tudo

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Isso sobe 3 serviços: **db** (PostgreSQL 16), **backend** (API na porta interna 8000) e **frontend** (nginx na porta 80, que também serve a API e o WebSocket via proxy).

### 5. Acessar

Na primeira inicialização, o sistema cria as tabelas e o **seed inicial**:

| Tela | URL |
|---|---|
| Kiosk (enfermagem/médico) | `http://IP-DO-SERVIDOR/unidade-havai` |
| Cozinha (Kanban) | `http://IP-DO-SERVIDOR/cozinha/1` |
| Entregas das copeiras | `http://IP-DO-SERVIDOR/entregas/1` |
| Administração | `http://IP-DO-SERVIDOR/admin` |
| Login | `http://IP-DO-SERVIDOR/login` |

**Utilizadores iniciais (trocar as senhas imediatamente!):**

| Perfil | E-mail | Senha |
|---|---|---|
| Admin TI | admin@hospital.local | `Trocar@123` |
| Nutricionista | nutricao@hospital.local | `Trocar@123` |
| Cozinha | cozinha@hospital.local | `Trocar@123` |

### 6. Comandos úteis

```bash
docker compose -f docker-compose.prod.yml logs -f backend   # ver logs
docker compose -f docker-compose.prod.yml down              # parar (dados ficam no volume)
docker compose -f docker-compose.prod.yml up -d --build     # atualizar após mudanças no código
docker exec dietas-db-prod pg_dump -U dietas dietas > backup.sql   # backup do banco
```

## Impressoras térmicas (ESC/POS)

No painel **Administração → Impressoras**, escolha a unidade e informe o IP da impressora térmica.
Clique em **Salvar impressora** e depois em **Testar conexão** para verificar a porta 9100 sem imprimir.
O servidor precisa **alcançar a impressora pela rede** (TCP porta 9100). Para testar conectividade a partir do servidor:

```bash
nc -zv IP-DA-IMPRESSORA 9100
```

A filipeta inclui os dados do solicitante e os campos dos formulários Médico e Enfermagem,
com os rótulos e a ordem configurados para cada unidade. **Sexo** e **Prontuário** são omitidos somente
na impressão; os valores continuam nos formulários e no pedido. Campos adicionados pelo gestor passam a sair
na impressão; valores antigos continuam visíveis mesmo se o campo for removido da configuração.
Campos configurados sem resposta mostram **Não informado**. Datas são apresentadas como `DD/MM/AAAA`,
dietas pelo nome e textos longos quebram conforme a largura do papel, sem truncar refeições,
nomes ou observações.

A fonte da filipeta usa **10 pontos** (28 pixels a 203 dpi), inclusive nos rótulos e nas observações.
Cabeçalhos e alertas mantêm o negrito. A largura útil comporta 31 caracteres por linha nesse tamanho;
o espaçamento entre linhas e a quebra dos textos são calculados pelas métricas da fonte.

Ao final dos dois tipos de filipeta, o bloco **Entrega à recepção** oferece espaço e linha para
**Assinatura**, além de **Data e hora** em branco para preenchimento manual no recebimento.
Esses campos não recebem a data/hora da solicitação automaticamente e também aparecem na reimpressão.

O texto é desenhado no servidor com **Pillow e DejaVu Sans Mono**, incluindo `ã, õ, ç, á`, e enviado
como imagem monocromática ESC/POS em blocos de até 128 linhas de pixels. Assim, os acentos não dependem
da tabela de caracteres interna da POS80. A área usada é de 576 pontos em papel de 80 mm; a impressora
deve aceitar [impressão raster GS v 0](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html).
As fontes e sua licença ficam em `backend/app/assets/fonts/`, incluídas também na imagem Docker.
Essa conversão acontece somente na impressão; os textos digitados permanecem preservados no banco.

O envio automático e o botão de reimpressão da Cozinha usam o mesmo gerador. A reimpressão consulta
os rótulos atuais da unidade e conserva todos os dados salvos no pedido. O alerta de restrição severa
e o corte de papel são mantidos. O informativo de horários do formulário não é repetido na filipeta.

## Segurança (checklist antes de ir a produção)

- [ ] Trocar as senhas dos 3 utilizadores do seed
- [ ] Definir `JWT_SECRET` forte no `.env`
- [ ] Definir `POSTGRES_PASSWORD` forte no `.env`
- [ ] Atualizar `CORS_ORIGINS` no `docker-compose.prod.yml` com o endereço real do sistema
- [ ] HTTPS: colocar um proxy reverso com TLS (ex.: nginx/Caddy) na frente, ou publicar só na rede interna
- [ ] Backup automático diário do volume `pgdata`

## Desenvolvimento (Windows)

Com Docker Desktop, Python 3.12 e Node.js instalados, execute na pasta do projeto:

```powershell
Set-Location 'C:\Users\Suporte\Documents\Projeto Cnutri'
.\start.ps1
```

O script inicia o PostgreSQL na porta **5433**, a API na **8000** e o frontend na **5173**.
Na primeira execução, cria o ambiente Python e instala as dependências que estiverem ausentes.
Execuções seguintes reutilizam os processos desta pasta. Os logs ficam em `work/logs/`.

- Formulário: `http://localhost:5173/unidade-havai`
- Cozinha: `http://localhost:5173/cozinha/1` (sem login)
- Entregas: `http://localhost:5173/entregas/1`
- Login: `http://localhost:5173/login`
- Pela rede: `http://IP-DESTA-MAQUINA:5173/unidade-havai`

Para encerrar ou reinstalar dependências:

```powershell
.\stop.ps1                         # encerra frontend e API
.\stop.ps1 -PararBanco             # encerra também o PostgreSQL
.\start.ps1 -InstalarDependencias  # reinstala com os serviços parados
```

O Compose de desenvolvimento mantém o nome `projeto-dietas-hospitalares`, associado ao volume
`projeto-dietas-hospitalares_pgdata`. Assim, mudar a pasta de trabalho preserva o banco existente.

O tema corporativo usa fundo `#808080`, painéis `#c8c8c8`, campos suaves e textos escuros. As cores
são centralizadas em `frontend/src/index.css`: `app-background`, `panel` e a escala neutra `slate`.
Botões de ação, estados de produção e alertas usam suas cores funcionais.

No painel **Gestão de Nutrição → Refeições médicas**, edite as listas de **Refeição**, **Suco**,
**Sobremesa** e **Local de entrega**, com uma opção por linha em cada campo, e clique em **Salvar opções**.
Essas listas alimentam o formulário médico, preservando a ordem e a obrigatoriedade dos campos.
As opções são salvas no banco de dados, sem alterar as dietas ou o formulário de Enfermagem.

## Painel de administração

O perfil **Administrador** entra diretamente em `/admin` após o login e tem acesso a todas as unidades.

- **Unidades:** criar, editar, ativar ou desativar unidades; abrir o formulário e o painel da cozinha;
  acessar a gestão de dietas, refeições, formulários e relatórios da unidade escolhida. Novas unidades
  recebem cópias independentes dos formulários e das dietas da unidade de origem selecionada.
- **Credenciais:** criar e editar nome, e-mail, senha, perfil e unidades de acesso; ativar ou desativar
  contas. Os perfis disponíveis são Administrador, Gestor de nutrição, Cozinha e Copeira. A própria conta
  administrativa não pode ser desativada nem perder seu perfil pelo mesmo usuário.
- **Impressoras:** associar uma impressora padrão por unidade, alterar/remover o IP e testar a conexão.

Gestão, administração, relatórios e o canal interno autenticado continuam verificando perfil e
unidades permitidas. O administrador pode retornar ao painel pelo link **Administração** nas telas
de Gestão e Cozinha.

## Cozinha, plantão e entregas no computador e no celular

O dashboard `/cozinha/{id}` e a página `/entregas/{id}` abrem sem login para unidades ativas.
Na cozinha, os pedidos passam por **Pendentes → Em preparo → Prontos**. No celular, botões de etapa
mostram uma coluna por vez; no computador, as três colunas aparecem juntas. A página de entregas
mostra somente as refeições prontas, em cartões com botão **Entregar**. Ambas usam botões de toque
de pelo menos 44 pixels e a caixa de seleção se ajusta à largura da tela.

Para cadastrar uma copeira, abra **Administração → Credenciais**, escolha o perfil **Copeira** e
vincule as unidades de trabalho. Nenhuma conta de copeira é criada automaticamente. Ela acessa
**Entrar no plantão** com a credencial cadastrada; enquanto a sessão estiver conectada, seu nome
fica disponível na unidade selecionada. A presença é renovada a cada 30 segundos. **Sair do plantão**
encerra a sessão imediatamente; fechar o navegador ou perder a conexão remove o nome após até
três minutos sem renovação. Sessões simultâneas da mesma pessoa não duplicam seu nome.

Ao tocar em **Entregar**, selecione uma copeira online e confirme. O servidor verifica novamente
se ela está no plantão e se o pedido continua pronto, grava nome, usuário, data/hora e origem da
entrega, e muda o pedido para **ENTREGUE**. Ele sai das listas de prontos e de entregas, mantendo
o histórico e os indicadores de consumo. Confirmações repetidas ou concorrentes são bloqueadas.

As rotas `/api/operacao` e o WebSocket `/ws/operacao/{id}` fornecem os dados operacionais para
essas telas. Prontuário, registro profissional, matrícula, sexo e data de nascimento não são
publicados nesse canal; a idade é calculada no servidor. O canal interno `/ws/cozinha/{id}` segue
restrito a perfis de operação autorizados. Atualização por consulta a cada dez segundos complementa
o WebSocket; a lista de copeiras é consultada a cada cinco segundos.

As tabelas `sessoes_copeiras` e `entregas_pedidos` e o perfil `COPEIRA` são criados na inicialização,
preservando usuários, pedidos e configurações existentes. O backup local anterior a essa atualização
fica em `backups/backup-dietas-2026-10-20-antes-entregas.dump`, fora do Git.

### Testes da administração, entregas e impressão

Os testes usam um banco SQLite temporário em memória, sem modificar o PostgreSQL em uso:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

São 31 testes: oito da administração, dez de operação/plantão/entrega e treze das filipetas.
Os testes de entrega cobrem presença por login, saída, expiração, unidades, registro único,
concorrência, proteção do canal interno e preservação do consumo após a entrega.
As verificações de filipeta incluem campos completos nos dois fluxos,
textos extensos, acentos, campos novos/antigos e igualdade entre impressão automática e reimpressão.
Os testes também reconstroem a imagem transmitida e conferem pixels, polaridade, limites dos blocos
e glifos diferentes para letras com e sem acento.
As impressoras são simuladas nesses testes; a saída em papel deve ser validada no equipamento real.

## Configuração dos formulários no GitHub

`configuracoes/formularios-unidade-havai.json` registra os esquemas Médico e Enfermagem em
19/10/2026, incluindo campos, ordem, obrigatoriedade, informativos e opções. O arquivo contém
somente a configuração dos formulários; pedidos, dados de pacientes, usuários e credenciais ficam fora dele.

As edições feitas no gestor continuam sendo gravadas no PostgreSQL. Atualize essa cópia ao sincronizar
novas alterações de formulário. Um `git pull` atualiza os arquivos e não substitui o banco em execução.

Para recuperar um esquema em outra instalação, autentique-se na API com um perfil de Gestão,
carregue `GET /api/gestao/formularios/{filial_id}/{tipo}` e envie o respectivo objeto
`formularios.MEDICO` ou `formularios.ENFERMAGEM` do JSON para
`PUT /api/gestao/formularios/{filial_id}/{tipo}`, em `esquema_json`. Inclua em `versao` o
`atualizado_em` retornado pelo GET para preservar a proteção contra edição concorrente.
