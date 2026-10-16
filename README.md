# Sistema de Gestão de Dietas Hospitalares

Plataforma multifilial para solicitação, preparo, entrega e auditoria de dietas hospitalares.

**Stack:** FastAPI (Python) · React + Vite · PostgreSQL 16 · WebSockets · Impressão ESC/POS · Docker

---

## Estrutura do projeto

```
projeto-dietas-hospitalares/
├── backend/                  # API FastAPI (app/), Dockerfile
├── frontend/                 # SPA React (src/), Dockerfile + nginx.conf
├── docker-compose.yml        # Desenvolvimento (só o PostgreSQL)
└── docker-compose.prod.yml   # Produção (banco + backend + frontend)
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

```powershell
docker compose up -d          # sobe só o PostgreSQL (porta 5433)
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --port 8000
cd ..\frontend
npm install
npm run dev                   # http://localhost:5173
```
