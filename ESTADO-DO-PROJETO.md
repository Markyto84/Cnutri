# 📋 Estado do Projeto — Documento de Continuidade

> **Instrução para o assistente:** este arquivo é a memória do projeto.
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

- **Pasta única nesta estação:** `C:\Users\Suporte\Documents\Projeto Cnutri` (unificada em 19/10/2026)
- **Backend:** FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 (JSONB)
- **Frontend:** React + Vite + Tailwind CSS 4, axios, react-router-dom
- **Impressão:** ESC/POS via socket TCP porta 9100 (sem dependência externa)
- **Dev (Windows):** `.\start.ps1` (Postgres na porta **5433**, backend na 8000, frontend na 5173)
- **Produção (Linux):** `docker compose -f docker-compose.prod.yml up -d --build` — nginx na porta 80
  com proxy de `/api` e `/ws`
- **Auth:** JWT; perfis: `ADMIN_TI`, `NUTRICIONISTA`, `COZINHA`

## 3. Como rodar (desenvolvimento)

Ver instruções completas no [README.md](README.md). Resumo Windows:

```powershell
Set-Location 'C:\Users\Suporte\Documents\Projeto Cnutri'
.\start.ps1                                # http://localhost:5173/unidade-havai
.\stop.ps1                                 # encerra frontend e API
```

## 4. Estado atual (o que já funciona)

- ✅ Formulário de Enfermagem com **14 campos na ordem**: Leito → Andar/Setor (lista) →
  Internado +6h? (Sim/Não) → Prontuário → Nome do Paciente → Matrícula → Data de Nascimento (data) →
  Sexo (MASCULINO/FEMININO) → Refeição (DESJEJUM/ALMOÇO/LANCHE DA TARDE/JANTAR/CEIA/KIT LANCHE) →
  Para (Paciente/Acompanhante/Paciente e Acompanhante) → Tipo de Dieta → **Cardápio** (dependente da
  dieta, por grupos) → **Líquido espessado** (NÉCTAR/MEL/PUDIM) → Restrições/Observações
- ✅ Cabeçalho institucional do formulário (horários de corte/serviço + aviso de fonoaudiologia),
  editável pelo painel
- ✅ Informativo em negrito abaixo do título do formulário Médico: “Solicitação de dieta até
  12:00 - Almoço e até as 18:00 - Jantar”, salvo no cabeçalho editável (19/10/2026)
- ✅ Campo “Equipe” logo abaixo do informativo médico, com botões de seleção única “Médica” e
  “Administração”; opções editáveis na Gestão e valor enviado em `dados_dinamicos.equipe` (19/10/2026)
- ✅ Campo “Horário de entrega” abaixo de Equipe no formulário médico, com 17 opções de 12:00
  a 20:00 a cada 30 minutos, enviado em `dados_dinamicos.horario_entrega` (19/10/2026)
- ✅ Campo “Refeição” médico com lista própria: PARMEGIANA DE  FRANGO COM ARROZ E BATATA SAUTÉE;
  MAMINHA ASSADA COM CANELONE DE RICOTA E ESPINAFRE. Escolha em `dados_dinamicos.refeicao` (19/10/2026)
- ✅ Abaixo de Refeição, listas obrigatórias de Suco (COM SUCO / SEM SUCO), Sobremesa
  (SOBREMESA DO DIA / SEM SOBREMESA) e Local de entrega (TÉRREO - CONFORTO MÉDICO /
  4º ANDAR - REFEITÓRIO), salvas em `dados_dinamicos` no formulário médico (19/10/2026)
- ✅ Aba “Refeições médicas” no gestor para editar as listas de Refeição, Suco, Sobremesa e Local
  de entrega, com uma opção por linha e proteção contra edição concorrente. Ordem, obrigatoriedade,
  demais campos, catálogo de dietas e formulário de Enfermagem preservados (19/10/2026)
- ✅ Card fixo no kiosk: Registro profissional + Solicitante (nome) — obrigatórios, dois fluxos
- ✅ Motor de formulários dinâmicos com tipos: `texto`, `texto_longo`, `data`, `selecao`, `radio`,
  `cardapio` (dependente de grupos de dieta), `selecao_dietas`
- ✅ Editor do formulário no painel (adicionar/remover/reordenar campos, editar cabeçalho)
- ✅ Cardápios preenchidos no banco: Grupo 1 (GERAL/BRANDA), 2 opções; Grupo 2
  (PASTOSA/PASTOSA LIQUIDIFICADA/BATIDA), 4 opções; Grupo 3 (LÍQUIDA/LIQUIDA SEM RESÍDUOS), 1 opção
- ✅ Catálogo de dietas: GERAL, BRANDA, LEVE, PASTOSA, PASTOSA LIQUIDIFICADA, BATIDA, LÍQUIDA,
  LIQUIDA SEM RESÍDUOS (Hipossódica e Enteral desativadas, preservando histórico)
- ✅ Editor de dietas (✏️ Editar: nome/descrição/severa; desativar/reativar)
- ✅ Kanban com idade do paciente calculada da data de nascimento, selos de refeição/cardápio/
  líquido espessado/para, alerta sonoro, reimpressão
- ✅ Relatórios: SLA (tempo médio), consumo do corpo médico por turno, volume por dieta
- ✅ Proteção contra edição concorrente do formulário (HTTP 409 + recarregar)
- ✅ Acesso em rede: `host: true` no Vite + regras de firewall (portas 5173 e 8000)
- ✅ Idioma da página corrigido para `pt-BR`, com `translate="no"` para preservar os rótulos e
  as opções originais diante da tradução automática do navegador (19/10/2026)
- ✅ Projeto unificado na pasta acima, com o histórico Git, dependências e banco preservados;
  os caminhos anteriores apontam para a mesma cópia (19/10/2026)
- ✅ Tema corporativo com fundo `#808080`, painéis `#c8c8c8`, campos suaves e textos escuros;
  alertas e botões mantêm cores funcionais. Paleta em `frontend/src/index.css` (19/10/2026)
- ✅ Pacote de produção para Linux: backend/Dockerfile, frontend/Dockerfile + nginx.conf,
  docker-compose.prod.yml, README com guia completo
- ✅ Backup do banco testado: `backups/backup-dietas-2026-10-16.sql` (não versionado)
- ✅ Backup adicional antes da unificação: `backups/backup-dietas-2026-10-19-antes-unificacao.dump`
- ✅ Configuração atual dos formulários Médico (7 campos) e Enfermagem (14 campos) exportada para
  `configuracoes/formularios-unidade-havai.json`, sem pedidos, pacientes ou credenciais (19/10/2026)
- ✅ Painel de Administração (`/admin`) com entrada automática para ADMIN_TI, abas Unidades,
  Credenciais e Impressoras; acesso à gestão e cozinha de todas as unidades (19/10/2026)
- ✅ Novas unidades copiam formulários e dietas da unidade escolhida e passam a ter configurações
  independentes. Nome, endereço do formulário e ativação podem ser editados pelo administrador
- ✅ Cadastro e edição de credenciais, senha, perfil e vínculos de unidades, com ativação/desativação
  e proteção da própria conta administrativa. API não expõe hashes de senha
- ✅ Impressora padrão por unidade, validação de IP e teste de conexão TCP 9100 sem imprimir
- ✅ Acesso de Gestão, Cozinha, relatórios e WebSocket limitado às unidades permitidas; ADMIN_TI tem
  acesso global. Sessão e saída sincronizadas entre abas do navegador
- ✅ Oito testes de integração administrativa em SQLite isolado, sem alterar o banco do hospital
- ✅ Filipeta da cozinha com todos os campos dos formulários Médico e Enfermagem, nome e registro
  do solicitante, rótulos/ordem de cada unidade e inclusão automática de novos campos. Dados antigos
  continuam visíveis mesmo após remoção do campo no gestor (20/10/2026)
- ✅ Textos da filipeta quebram em linhas de 42 colunas, sem truncar nomes, refeições, cardápios ou
  observações; datas em DD/MM/AAAA, acentos PC850 e campos configurados vazios como “Não informado”
- ✅ Impressão automática e reimpressão usam o mesmo gerador; dez testes de impressão adicionados,
  totalizando 18 testes isolados. Validação em papel depende da impressora real (20/10/2026)

## 5. Pendências / decisões em aberto

1. **Dietas severas:** nenhuma marcada com destaque vermelho ainda
2. **Impressora térmica real:** IP já cadastrado na unidade Havaí; validar a nova filipeta em papel
3. **Senhas do seed** precisam ser trocadas antes de produção
   (admin@hospital.local / nutricao@hospital.local / cozinha@hospital.local — senha `Trocar@123`)
4. **Líquido espessado:** hoje é opcional e aparece sempre — avaliar se deve ser obrigatório
   ou dependente de grupo de dieta
5. **Ideia sugerida (não confirmada):** filtro/colunas por refeição no Kanban
6. **Produção:** HTTPS (proxy reverso), backup agendado diário, CORS_ORIGINS com URL real

## 6. Convenções técnicas importantes (não quebrar)

- **Campos dinâmicos:** campos do formulário que não são "fixos" do backend vão para
  `pedidos.dados_dinamicos` (JSONB). Fixos: `leito`, `prontuario`, `nome_paciente`, `dieta_id`,
  `observacoes_alergias`, `solicitante_nome` (lista no `Kiosk.jsx`, constante `fixos`)
- **Editor de listas:** textareas trabalham com texto CRU durante a digitação (Enter preservado);
  conversão para lista só no `montarPayload()` ao publicar — não reintroduzir o filtro por tecla
- **Filipetas:** `montar_filipeta_configurada()` carrega o esquema da unidade e do fluxo (PACIENTE →
  ENFERMAGEM). Usar esse caminho no envio e na reimpressão; não manter listas de campos separadas
  nas rotas. Campos extras salvos também são impressos; o informativo estático de horários fica no kiosk
- **Proteção de edição:** o PUT de formulários exige `versao` (timestamp `atualizado_em` carregado);
  divergência → 409. Ao salvar no editor, recarrega a versão nova
- **SQLAlchemy async:** relacionamentos usados em contexto async precisam de `selectinload`
  (evita MissingGreenlet)
- **Timestamps:** usar `func.now()` do banco em colunas `TIMESTAMP` (asyncpg rejeita datetime
  com timezone em coluna naive)
- **Encoding no Windows:** cuidado com acentos em heredocs/stdin do Git Bash ao atualizar dados
  via script — preferir arquivos JSON lidos com `encoding='utf-8'`
- **Idioma no navegador:** manter `lang="pt-BR"` e `translate="no"` no HTML. Rótulos corretos na
  API podem aparecer trocados se o navegador traduzir a página; validar também o acesso pelo IP
- **Estrutura única:** editar a pasta canônica indicada na seção 2. Os caminhos anteriores são
  junções para ela; as versões arquivadas ficam fora do projeto. O nome do Compose mantém o volume do banco
- **Tema:** manter a escala neutra no `@theme` de `frontend/src/index.css`; usar as classes existentes
  para que kiosk, login, cozinha, gestão e administração compartilhem a mesma paleta
- **Slug da filial:** `unidade-havai` (URL dos quiosques); mudar slug quebra links antigos

## 7. Dados do banco (fonte da verdade)

O PostgreSQL é a fonte da verdade para configurações de formulário, dietas e pedidos. A cópia
`configuracoes/formularios-unidade-havai.json` versiona somente os esquemas dos formulários e deve
ser atualizada após alterações pelo gestor. Ela não é aplicada automaticamente por `git pull`;
para recuperar esquemas em outro ambiente, use a API de Gestão conforme o README, com `versao`.
Dados de pacientes, pedidos, usuários e backups completos ficam fora do Git.
Para migrar/backup:

```bash
docker exec dietas-db pg_dump -U dietas dietas > backups/backup-$(date +%F).sql
cat backups/backup-XXXX.sql | docker exec -i dietas-db-prod psql -U dietas -d dietas   # restaurar
```

## 8. Fluxo de trabalho (multi-estação)

- Código: `git pull` antes de editar → alterar → testar → `git push` (GitHub: Markyto84/Cnutri)
- Formulários: atualizar a cópia de configuração versionada ao sincronizar alterações feitas no painel
- Dados: em produção, um único banco no servidor central acessado por todos via navegador
- Ao concluir mudanças relevantes, **atualizar este arquivo** (seção 4 e 5)
