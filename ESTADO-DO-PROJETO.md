# 📋 Estado do Projeto — Documento de Continuidade

> **Instrução para o assistente:** este arquivo é a memória do projeto.
> Ao iniciar uma sessão nova em qualquer estação, leia-o primeiro para retomar o contexto.

## 1. O que é o sistema

**Sistema Web de Gestão de Dietas Hospitalares** — plataforma multifilial para solicitação,
preparo, entrega e auditoria de refeições/dietas hospitalares.

- **Kiosk público** (`/unidade-havai`): postos de enfermagem/médico, sem login, rastreabilidade
  por registro profissional (CRM/COREN/Matrícula) + nome do solicitante
- **Painel da Cozinha** (`/cozinha/1`): consulta pública com ações autenticadas, Kanban em tempo real (WebSocket),
  alerta sonoro, destaque para dietas severas, reimpressão de filipetas; responsivo para celular
- **Entregas das copeiras** (`/entregas/1`): refeições prontas, seleção de copeira online por login
  e recebimento com nome/assinatura, responsável e horário; responsivo para celular
- **Gestão de Nutrição** (`/gestao`): catálogo de dietas, motor de formulários dinâmicos, relatórios
- **Admin TI** (`/admin`): filiais, IPs de impressoras, usuários/perfis (RBAC) e relatórios de todas as unidades

## 2. Stack e arquitetura

- **Pasta única nesta estação:** `C:\Users\Suporte\Documents\Projeto Cnutri` (unificada em 19/10/2026)
- **Backend:** FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 (JSONB)
- **Frontend:** React + Vite + Tailwind CSS 4, axios, react-router-dom
- **Impressão:** ESC/POS via socket TCP porta 9100 (sem dependência externa)
- **Dev (Windows):** `.\start.ps1` (Postgres na porta **5433**, backend na 8000, frontend na 5173)
- **Produção (Linux):** `docker compose -f docker-compose.prod.yml up -d --build` — nginx na porta 80
  com proxy de `/api` e `/ws`
- **Auth:** JWT; perfis: `ADMIN_TI`, `NUTRICIONISTA`, `COZINHA`, `COPEIRA`

## 3. Como rodar (desenvolvimento)

Ver instruções completas no [README.md](README.md). Resumo Windows:

```powershell
Set-Location 'C:\Users\Suporte\Documents\Projeto Cnutri'
.\start.ps1                                # http://localhost:5173/unidade-havai
.\stop.ps1                                 # encerra frontend e API
```

## 4. Estado atual (o que já funciona)

- ✅ Etiquetas de 89 mm × 36 mm com unidade, paciente, matrícula, refeição e cardápio.
  Cadastro por unidade em Administração → Impressoras, com modelo/IP/porta/ZPL ou TSPL/dpi.
  Botão e prévia na cozinha somente em Prontos, com autorização e conferência do status também
  no servidor/consumidor. Fila independente da filipeta, acentos rasterizados e reenvio controlado.
  Nenhum IP de etiquetas ativado automaticamente; usuário ainda não possui os modelos/IPs.
  Validação mais recente: 91 testes de backend, onze de frontend e build aprovados.
  Detalhes e homologação física pendente em [ETIQUETAS.md](ETIQUETAS.md).

- ✅ Política de senhas novas ajustada a pedido do usuário: de 8 a 12 caracteres, com uma
  maiúscula, um número e um caractere especial, no cadastro, reset e troca de senha. Gerador
  de temporárias usa 12 caracteres; senhas existentes continuam válidas. Posteriormente, em
  20/10/2026, o usuário solicitou redefinir admin: nova temporária entregue em arquivo privado
  em work/, login conferido e troca obrigatória no próximo acesso. Sessões anteriores encerradas;
  demais contas preservadas. O arquivo antigo de acessos não contém a senha atual de admin.
  Validação atual: 80 testes de backend e onze de frontend, incluindo limites e composição.

- ✅ Itens 4–9 do review aplicados em 20/10/2026: sessões revogadas também fecham canais
  privados; revalidação periódica do WebSocket detecta expiração sem mensagens do cliente.
- ✅ Fila de impressão persistida, processamento em segundo plano, até três tentativas de
  conexão e conferência obrigatória antes de reenviar transmissões incertas. Cozinha e kiosk
  mostram o estado real do envio; transmissão TCP não confirma a saída física do papel.
- ✅ Solicitações protegidas por chave UUID por unidade: repetir retorna o pedido original,
  sem duplicar pedido, impressão ou evento; a confirmação mostra o número e permite recuperação.
- ✅ Turnos médicos calculados em Brasília; resumo/exportações distinguem unidades e dietas
  homônimas por IDs, exibindo o código da unidade. Docker da API fixado em um worker.
- ✅ Validação atual: 76 testes de backend (seis PostgreSQL), oito de frontend e build aprovados;
  lint com dois avisos anteriores em Gestao.jsx. Conferência desktop/mobile com dados fictícios.
  Backup anterior validado e integridade dos dados preservada. Detalhes em
  [ESTABILIZACAO-ITENS-4-9.md](ESTABILIZACAO-ITENS-4-9.md).
- ⏳ Item 10 adiado pelo usuário para outro servidor, com domínio e certificado da TI.
  Não ativar HTTPS/supervisão nesta estação sem retomar essa etapa. A URL atual continua
  `http://10.1.140.15:5173`.

- ✅ Itens 1–3 do review de 20/10/2026: segredo JWT privado sem padrão; senhas iniciais rotacionadas
  por ferramenta com arquivo de entrega privado; primeiro acesso exige nova senha; produção bloqueia configuração insegura.
- ✅ Tentativas de autenticação limitadas e registradas; sessões persistidas para todos os perfis,
  revogadas no logout e na troca/reset de senha. Canais internos são fechados no processo atual da API.
- ✅ Dashboards públicos para consulta; preparo/cancelamento/reimpressão exigem Cozinha/Gestão/TI e vínculo;
  entrega exige Copeira própria ou Gestão/TI com copeira online. Histórico registra o operador real.
- ✅ Relatórios e exportações distinguem copeira responsável e usuário que registrou a entrega;
  entregas antigas preservadas, sem atribuição presumida de operador.
- ✅ Validação de pedidos no servidor pelo formulário vigente: obrigatórios, opções, cardápio por dieta,
  datas, comprimentos e dieta ativa da unidade. Solicitante e registro profissional não podem ficar em branco.
- ✅ Tela `/senha`, limites nos campos e obrigatoriedade dos textos longos no frontend.
  Validação: 59 testes do backend (três com PostgreSQL), quatro do frontend, build e conferência desktop/mobile com dados fictícios.
  Detalhes em [SEGURANCA-ITENS-1-3.md](SEGURANCA-ITENS-1-3.md).


- ✅ Título da aba do navegador definido como **Cnutri** em todas as páginas (20/10/2026)
- ✅ Ícone da aba baseado na imagem enviada pelo usuário, com nitidez melhorada e sem os pontos
  azuis à esquerda. Versão atual em `frontend/public/cnutri-icon-v2.png`, aplicada a todas as páginas
  pelo HTML principal; imagem original preservada em `cnutri-icon.png` (20/10/2026)
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
- ✅ Tema corporativo Blue `#0070AD` e Vibrant Blue `#17ABDA`, fundo suave `#EDF5FA`, painéis
  brancos e campos/textos em tons azulados. Paleta em `frontend/src/index.css`, substituindo
  o tema cinza anterior (20/10/2026)
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
- ✅ Acesso de Gestão, relatórios e WebSocket interno limitado a perfis e unidades permitidas;
  ADMIN_TI tem acesso global. Sessão e saída sincronizadas entre abas do navegador
- ✅ Oito testes de integração administrativa em SQLite isolado, sem alterar o banco do hospital
- ✅ Filipeta da cozinha com os campos dos formulários Médico e Enfermagem (exceto Sexo e Prontuário), nome e registro
  do solicitante, rótulos/ordem de cada unidade e inclusão automática de novos campos. Dados antigos
  continuam visíveis mesmo após remoção do campo no gestor (20/10/2026)
- ✅ Textos da filipeta quebram conforme a largura útil do papel, sem truncar nomes, refeições, cardápios ou
  observações; datas em DD/MM/AAAA e campos configurados vazios como “Não informado”
- ✅ Impressão automática e reimpressão usam o mesmo gerador; dez testes de impressão adicionados,
  totalizando 18 testes isolados. Validação em papel depende da impressora real (20/10/2026)
- ✅ Correção de `ã, õ, ç, á` na POS80: textos desenhados no servidor e enviados como imagem
  monocromática ESC/POS (GS v 0), sem depender de code page. Pillow e fontes DejaVu Sans Mono
  distribuídas com o backend; área de 576 pontos, blocos de até 128 linhas de pixels (20/10/2026)
- ✅ Três testes de imagem adicionados, totalizando 21 testes: pixels/polaridade e divisão dos blocos,
  glifos de acentos e preservação de símbolos e de filipetas extensas
- ✅ Duas filipetas de teste enviadas à POS80 em 20/10/2026; usuário confirmou em papel que
  “ã õ ç á | ação, maçã, coração” saíram corretamente após a correção
- ✅ Fonte da filipeta ajustada para 10 pontos (28 pixels a 203 dpi), com cabeçalhos e alertas em
  negrito. Largura de 31 caracteres e espaçamento calculados pela fonte, mantendo textos completos
  na impressão e na reimpressão (20/10/2026)
- ✅ Sexo e Prontuário omitidos somente da filipeta, preservados nos formulários e nos pedidos.
  Rodapé “Entrega à recepção” com espaço para assinatura e data/hora em branco para preenchimento
  manual, presente nos dois fluxos e na reimpressão (20/10/2026)
- ✅ Dashboard da cozinha e página de entregas públicos por unidade ativa. API e WebSocket
  operacionais excluem prontuário, registro profissional, matrícula, sexo e nascimento; a idade
  é calculada no servidor. Gestão e administração continuam protegidas (20/10/2026)
- ✅ Perfil COPEIRA disponível em Administração → Credenciais, com vínculos por unidade. Login
  abre o plantão, heartbeat de 30 segundos renova a presença por três minutos e logout encerra
  a sessão. Nomes disponíveis somente na unidade do plantão, sem duplicar sessões da pessoa
- ✅ Página `/entregas/{id}` mostra somente PRONTO; botão Entregar abre seleção de copeira online.
  Confirmação grava usuário/nome/horário/IP em `entregas_pedidos`, histórico e status ENTREGUE.
  Pedido sai das listas de prontos; atualizações concorrentes e entrega duplicada são bloqueadas
- ✅ Cozinha e entregas adaptadas para computador e celular: etapas em abas no celular, cartões
  em uma coluna, controles de pelo menos 44 pixels e diálogo ajustado à tela. Fluxo verificado
  no navegador com pedidos e credenciais fictícios em banco separado, sem alterar pedidos reais
- ✅ Relatório de consumo médico mantém refeições após entrega. Dez testes novos de operação
  totalizam 31 testes aprovados, além do build do frontend e lint dos arquivos alterados
- ✅ Backup antes das entregas: `backups/backup-dietas-2026-10-20-antes-entregas.dump`, validado
  com pg_restore, fora do Git. Novas tabelas e perfil criados no startup; nenhuma copeira real
  cadastrada automaticamente
- ✅ Entrega em duas etapas: copeira online → nome e assinatura do recebedor, com desenho por
  toque/caneta/mouse, limpeza e preservação ao redimensionar a tela. Finalização exige assinatura
  válida; nome, PNG e entrega são salvos na mesma transação, com data/hora do banco (20/10/2026)
- ✅ Relatórios da gestão incluem entregas e comprovantes: destinatário, refeição, copeira,
  recebedor, local/leito, data e hora da finalização e botão Ver assinatura. Filtros de data em
  Brasília e paginação de 50 itens. API e imagem exigem Gestão/Admin e unidade permitida;
  nenhum comprovante é enviado ao dashboard ou ao WebSocket público
- ✅ Nova tabela `recebimentos_entregas` criada no startup, sem alterar os registros antigos;
  recebimentos anteriores continuam no relatório como sem assinatura. Backup validado antes da
  atualização: `backups/backup-dietas-2026-10-20-antes-assinaturas.dump`, fora do Git
- ✅ Quatro testes de assinatura/relatório adicionados, totalizando 35: validação, gravação e
  horário do servidor, permissões, virada de data em Brasília, legado e rollback de falha.
  Desenho, limpeza e consulta do comprovante verificados em telas de 320 e 390 pixels, com
  dados fictícios em banco separado; frontend compilado e arquivos novos sem avisos de lint
- ✅ Relatório de dietas e solicitações em Gestão → Relatórios e Administração → Relatórios,
  com data/hora inicial e final em Brasília, período por solicitação ou entrega, formulário e
  situação. Gestão limitada à unidade permitida; administração com uma ou todas as unidades,
  inclusive inativas. Totais por unidade/dieta e detalhes paginados de 25 registros (20/10/2026)
- ✅ Exportação de todos os registros filtrados para Excel (.xlsx), Calc (.ods) e Google Sheets
  (.csv para Arquivo → Importar). XLSX/ODS com abas Resumo e Solicitações, datas/números tipados,
  acentos e texto completo; CSV com UTF-8 BOM. Inclui campos dinâmicos, horários de preparo/entrega,
  copeira, recebedor e indicação de assinatura, sem imagem nem prontuário/sexo/nascimento/matrícula
- ✅ Textos semelhantes a fórmulas permanecem texto nos arquivos. Campos acima de 32.767 caracteres
  geram orientação para CSV/ODS em vez de truncamento silencioso no XLSX. Dependências portáveis
  openpyxl e odfpy em requirements.txt; nenhuma alteração no esquema do banco para o relatório
- ✅ Sete testes de relatório adicionados, totalizando 42 aprovados; build do frontend aprovado.
  Filtros de horário, escopo de gestor/admin, três downloads e tela móvel de 390 pixels verificados
  no navegador com dados fictícios. XLSX importado e renderizado para conferência visual das abas
- ✅ Serviços restabelecidos após API e frontend serem encerrados junto do terminal de trabalho.
  start.ps1 inicia serviços ausentes em sessão independente via WMI e janela oculta, preservando
  estado de processos para stop.ps1. Verificado acesso pela rede em 5173 e saúde da API; não há
  inicialização automática após reiniciar o Windows (20/10/2026)
- ✅ Login alterado de e-mail para nome de usuário definido em Administração → Credenciais,
  com senha, nome completo e perfil separados. Nomes de 3 a 50 caracteres (letras sem acento,
  números, ponto, hífen e sublinhado), sem distinguir maiúsculas/minúsculas e com unicidade no
  banco. Novas contas dispensam e-mail; login antigo por e-mail deixa de ser aceito (20/10/2026)
- ✅ Migração PostgreSQL automática em `core/login_usuarios.py`: adiciona `nome_usuario`, deriva
  nomes iniciais do e-mail legado, resolve colisões com sufixo e preserva nomes já definidos.
  Senhas, IDs, perfis, vínculos e sessões mantidos. Quatro contas atuais migradas; acesso TI inicial
  com `admin` e a senha existente. Conferência de integridade antes/depois preservando os dados originais
- ✅ Backup validado antes do login por usuário: `backups/backup-dietas-2026-10-20-173506-antes-login-usuario.dump`,
  fora do Git. Quatro testes adicionais (46 aprovados), incluindo migração em schema PostgreSQL
  isolado com rollback; frontend compilado e Login/Admin sem avisos de lint
- ✅ Nova paleta aplicada a login, formulários Médico/Enfermagem, gestão, administração, relatórios,
  dashboard da cozinha e entregas. Cabeçalhos com borda Vibrant Blue, ações principais Blue e
  destaques/entregas/exportação Vibrant Blue com texto escuro; alertas e indicadores funcionais
  mantêm identificação própria. Contraste de texto de 5,36:1 no Blue e 4,92:1 no Vibrant Blue
- ✅ Cores exatas conferidas no navegador, seleção de equipe e telas administrativas/operacionais
  revisadas com dados fictícios. Cozinha e entregas verificadas em 390 pixels, sem rolagem horizontal.
  Compilação do frontend aprovada; lint com três avisos preexistentes. Atualização visual servida
  pelo Vite sem reiniciar os serviços ou alterar dados do banco (20/10/2026)

## 5. Pendências / decisões em aberto

1. **Dietas severas:** nenhuma marcada com destaque vermelho ainda
2. **Credenciais:** senhas iniciais substituídas por temporárias fortes, fora do Git. Os responsáveis devem definir suas senhas no próximo acesso.
3. **Líquido espessado:** hoje é opcional e aparece sempre — avaliar se deve ser obrigatório
   ou dependente de grupo de dieta
4. **Ideia sugerida (não confirmada):** filtro/colunas por refeição no Kanban
5. **Produção / item 10:** adiado pelo usuário para outro servidor; já há domínio e certificado
   da TI. Retomar HTTPS, início/recuperação automáticos, prontidão do banco, restrições de rede,
   credencial do banco, backup agendado e CORS_ORIGINS com a URL definitiva nessa instalação.

## 6. Convenções técnicas importantes (não quebrar)

- **Campos dinâmicos:** campos do formulário que não são "fixos" do backend vão para
  `pedidos.dados_dinamicos` (JSONB). Fixos: `leito`, `prontuario`, `nome_paciente`, `dieta_id`,
  `observacoes_alergias`, `solicitante_nome` (lista no `Kiosk.jsx`, constante `fixos`)
- **Editor de listas:** textareas trabalham com texto CRU durante a digitação (Enter preservado);
  conversão para lista só no `montarPayload()` ao publicar — não reintroduzir o filtro por tecla
- **Filipetas:** `montar_filipeta_configurada()` carrega o esquema da unidade e do fluxo (PACIENTE →
  ENFERMAGEM). Usar esse caminho no envio e na reimpressão; não manter listas de campos separadas
  nas rotas. Campos extras salvos também são impressos; o informativo estático de horários fica no kiosk
- **Fila de impressão:** pedido e trabalho são persistidos juntos; TCP somente no consumidor em
  segundo plano. PENDENTE/PROCESSANDO são únicos por pedido; INCERTO exige conferência explícita.
  Não interpretar ENVIADO como confirmação física e não enfileirar registros antigos na migração.
- **Repetição de envio:** manter `Idempotency-Key` por tentativa, unicidade por filial e hash do
  conteúdo original. Não gerar outra chave no retry nem repetir impressão/evento no replay.
- **API:** um único worker enquanto conexões/eventos WebSocket estiverem em memória. Escalar
  exige compartilhar tanto os eventos quanto a revogação de canais entre os processos.
- **Recebimento:** os IDs `sexo` e `prontuario` são ocultados somente no gerador da filipeta. O rodapé
  tem Assinatura e Data e hora para preenchimento manual; preservar os dados originais nos pedidos
- **Operação pública:** usar `/api/operacao` e `/ws/operacao/{id}` com projeção explícita dos dados
  operacionais. O canal interno `/ws/cozinha/{id}` exige perfil de operação, JWT e unidade permitida
- **Entregas:** somente PRONTO pode virar ENTREGUE, com copeira online vinculada à unidade.
  Manter UPDATE condicionado ao status anterior e chave única por pedido; rotas internas também
  não podem sobrescrever ENTREGUE. Preservar `concluido_em` (fim do preparo) para o SLA
- **Assinatura:** `EntregaCreate` exige nome do recebedor e traços normalizados; o servidor gera
  o PNG e salva em `recebimentos_entregas` na mesma transação da entrega. Não aceitar timestamp
  enviado pelo navegador. Consulta de comprovantes somente nos endpoints autenticados de relatório
- **Relatório de dietas:** consulta e exportação usam os mesmos filtros e permissões em
  `/api/relatorios/dietas-periodo`. Exportar todas as linhas, sem limitar à página da tela;
  resumo e detalhes do arquivo vêm do mesmo conjunto de registros. Horários em Brasília;
  Google Sheets recebe CSV por importação manual, sem publicação ou envio de dados à nuvem
- **Processos locais:** start.ps1 inicia serviços ausentes via sessão WMI independente do terminal.
  Preservar validação de pasta/porta e PID/data de criação no stop.ps1; não encerrar processos
  por nome nem iniciar uma segunda cópia contra o mesmo banco. Logs e estado ficam fora do Git
- **Plantão:** sessões COPEIRA usam JWT com `jti`, presença persistida por três minutos e renovação
  a cada 30 segundos. Logout fecha a sessão; atividade em uma unidade não publica presença em outra
- **Acentos na impressão:** `compor_linhas_filipeta()` mantém o texto Unicode, e `impressao_raster.py`
  desenha as letras com as fontes versionadas em `app/assets/fonts/`. Não voltar ao envio de caracteres
  CP850/CP437 à POS80: a tabela interna do equipamento substitui os acentos por outros glifos
- **Proteção de edição:** o PUT de formulários exige `versao` (timestamp `atualizado_em` carregado);
  divergência → 409. Ao salvar no editor, recarrega a versão nova
- **Login:** autenticar por `usuarios.nome_usuario` normalizado, nunca por e-mail. O índice único
  `uq_usuarios_nome_usuario` usa lower(nome_usuario); somente ADMIN_TI cria/edita nomes de acesso.
  Preservar IDs, senhas personalizadas, nomes já escolhidos pela TI e vínculo do JWT por ID
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
- **Tema:** usar os tokens `brand` (#0070AD), `brand-vibrant` (#17ABDA), `brand-ink` e a escala azulada
  no `@theme` de `frontend/src/index.css`. Texto branco no Blue e escuro no Vibrant Blue. Cabeçalhos
  compartilham `brand-header`; conservar as cores funcionais de erros, restrições e estados de produção
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
