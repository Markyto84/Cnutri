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

No painel **Admin → Filiais → 🖨️ IP**, informe o IP da impressora de cada unidade.
O servidor precisa **alcançar a impressora pela rede** (TCP porta 9100). Para testar conectividade a partir do servidor:

```bash
nc -zv IP-DA-IMPRESSORA 9100
```

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
