# 📋 Estado do Projeto — Documento de Continuidade

> **Instrução para o assistente (Bionic/LM Studio):** este arquivo é a memória do projeto.
> Ao iniciar uma sessão nova em qualquer estação, leia-o primeiro para retomar o contexto.

## 1. O que é o sistema

**Sistema Web de Gestão de Dietas Hospitalares** — plataforma multifilial para solicitação,
preparo, entrega e auditoria de refeições/dietas hospitalares.

- **Kiosk público** (`/unidade-havai`): postos de enfermagem/médico, sem login, rastreabilidade
  por registro profissional (CRM/COREN/Matrícula) + nome do solicitante
- **Painel da Cozinha** (`/cozinha/1`): Kanban em tempo real (WebSocket), alerta sonoro,
  destaque vermelho para dietas severas, reimpressão de filipetas
- **Gestão de Nutrição** (`/gestao`): catálogo de dietas, motor de formulários dinâmicos, relatórios
- **Admin TI** (`/admin`): filiais, IPs de impressoras, usuários/perfis (RBAC)

## 2. Stack e arquitetura

- **Backend:** FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 (JSONB)
- **Frontend:** React + Vite + Tailwind CSS 4, axios, react-router-dom
- **Impressão:** ESC/POS via socket TCP porta 9100 (sem dependência externa)
- **Dev (Windows):** `docker compose up -d` (só o Postgres na porta **5433**), backend na 8000, frontend na 5173
- **Produção (Linux):** `docker compose -f docker-compose.prod.yml up -d --build` — nginx na porta 80
  com proxy de `/api` e `/ws`
- **Auth:** JWT; perfis: `ADMIN_TI`, `NUTRICIONISTA`, `COZINHA`

## 3. Como rodar (desenvolvimento)

Ver instruções completas no [README.md](README.md). Resumo Windows:

```powershell
docker compose up -d                      # Postgres (porta 5433)
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --port 8000
cd ..\frontend
npm install
npm run dev                               # http://localhost:5173
```

## 4. Estado atual (o que já funciona)

- ✅ Formulário de Enfermagem com **14 campos na ordem**: Leito → Andar/Setor (lista) →
  Internado +6h? (Sim/Não) → Prontuário → Nome do Paciente → Matrícula → Data de Nascimento (data) →
  Sexo (MASCULINO/FEMININO) → Refeição (DESJEJUM/ALMOÇO/LANCHE DA TARDE/JANTAR/CEIA/KIT LANCHE) →
  Para (Paciente/Acompanhante/Paciente e Acompanhante) → Tipo de Dieta → **Cardápio** (dependente da
  dieta, por grupos) → **Líquido espessado** (NÉCTAR/MEL/PUDIM) → Restrições/Observações
- ✅ Cabeçalho institucional do formulário (horários de corte/serviço + aviso de fonoaudiologia),
  editável pelo painel
- ✅ Card fixo no kiosk: Registro profissional + Solicitante (nome) — obrigatórios, dois fluxos
- ✅ Motor de formulários dinâmicos com tipos: `texto`, `texto_longo`, `data`, `selecao`,
  `cardapio` (dependente de grupos de dieta), `selecao_dietas`
- ✅ Editor do formulário no painel (adicionar/remover/reordenar campos, editar cabeçalho)
- ✅ Catálogo de dietas: GERAL, BRANDA, LEVE, PASTOSA, PASTOSA LIQUIDIFICADA, BATIDA, LÍQUIDA,
  LIQUIDA SEM RESÍDUOS (Hipossódica e Enteral desativadas, preservando histórico)
- ✅ Editor de dietas (✏️ Editar: nome/descrição/severa; desativar/reativar)
- ✅ Kanban com idade do paciente calculada da data de nascimento, selos de refeição/cardápio/
  líquido espessado/para, alerta sonoro, reimpressão
- ✅ Relatórios: SLA (tempo médio), consumo do corpo médico por turno, volume por dieta
- ✅ Proteção contra edição concorrente do formulário (HTTP 409 + recarregar)
- ✅ Acesso em rede: `host: true` no Vite + regras de firewall (portas 5173 e 8000)
- ✅ Pacote de produção para Linux: backend/Dockerfile, frontend/Dockerfile + nginx.conf,
  docker-compose.prod.yml, README com guia completo
- ✅ Backup do banco testado: `backups/backup-dietas-2026-10-16.sql` (não versionado)

## 5. Pendências / decisões em aberto

1. **Itens dos cardápios** dos Grupos 1, 2 e 3 ainda vazios:
   - Grupo 1 → dietas GERAL, BRANDA
   - Grupo 2 → dietas PASTOSA, PASTOSA LIQUIDIFICADA, BATIDA
   - Grupo 3 → dietas LÍQUIDA, LIQUIDA SEM RESÍDUOS
2. **Dietas severas:** nenhuma marcada com destaque vermelho ainda
3. **Impressora térmica real:** configurar o IP no painel Admin → Filiais
4. **Senhas do seed** precisam ser trocadas antes de produção
   (admin@hospital.local / nutricao@hospital.local / cozinha@hospital.local — senha `Trocar@123`)
5. **Líquido espessado:** hoje é opcional e aparece sempre — avaliar se deve ser obrigatório
   ou dependente de grupo de dieta
6. **Ideia sugerida (não confirmada):** filtro/colunas por refeição no Kanban
7. **Produção:** HTTPS (proxy reverso), backup agendado diário, CORS_ORIGINS com URL real

## 6. Convenções técnicas importantes (não quebrar)

- **Campos dinâmicos:** campos do formulário que não são "fixos" do backend vão para
  `pedidos.dados_dinamicos` (JSONB). Fixos: `leito`, `prontuario`, `nome_paciente`, `dieta_id`,
  `observacoes_alergias`, `solicitante_nome` (lista no `Kiosk.jsx`, constante `fixos`)
- **Editor de listas:** textareas trabalham com texto CRU durante a digitação (Enter preservado);
  conversão para lista só no `montarPayload()` ao publicar — não reintroduzir o filtro por tecla
- **Proteção de edição:** o PUT de formulários exige `versao` (timestamp `atualizado_em` carregado);
  divergência → 409. Ao salvar no editor, recarrega a versão nova
- **SQLAlchemy async:** relacionamentos usados em contexto async precisam de `selectinload`
  (evita MissingGreenlet)
- **Timestamps:** usar `func.now()` do banco em colunas `TIMESTAMP` (asyncpg rejeita datetime
  com timezone em coluna naive)
- **Encoding no Windows:** cuidado com acentos em heredocs/stdin do Git Bash ao atualizar dados
  via script — preferir arquivos JSON lidos com `encoding='utf-8'`
- **Slug da filial:** `unidade-havai` (URL dos quiosques); mudar slug quebra links antigos

## 7. Dados do banco (fonte da verdade)

O Git **não versiona dados**. Configurações de formulário, dietas e pedidos vivem no PostgreSQL.
Para migrar/backup:

```bash
docker exec dietas-db pg_dump -U dietas dietas > backups/backup-$(date +%F).sql
cat backups/backup-XXXX.sql | docker exec -i dietas-db-prod psql -U dietas -d dietas   # restaurar
```

## 8. Fluxo de trabalho (multi-estação)

- Código: `git pull` antes de editar → alterar → testar → `git push` (GitHub: Markyto84/Cnutri)
- Dados: em produção, um único banco no servidor central acessado por todos via navegador
- Ao concluir mudanças relevantes, **atualizar este arquivo** (seção 4 e 5)
