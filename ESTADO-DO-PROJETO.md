# 📋 Estado do Projeto — Documento de Continuidade

> **Instrução para o assistente:** este arquivo é a memória do projeto.
> Ao iniciar uma sessão nova em qualquer estação, leia-o primeiro para retomar o contexto.

## 1. O que é o sistema

**Sistema Web de Gestão de Dietas Hospitalares** — plataforma multifilial para solicitação,
preparo, entrega e auditoria de refeições/dietas hospitalares.

- **Kiosk público** (`/unidade-havai`): postos de enfermagem/médico, sem login, rastreabilidade
  por registro profissional (CRM/COREN/Matrícula) + nome do solicitante
- **Painel da Cozinha** (`/cozinha/1`): consulta e operação sem login, Kanban em tempo real (WebSocket),
  alerta sonoro, destaque para dietas severas, reimpressão de filipetas; responsivo para celular
- **Entregas das copeiras** (`/entregas/1`): refeições prontas, copeira identificada pelo login
  e finalização direta com responsável e horário; assinaturas anteriores preservadas; responsivo para celular
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

- ✅ **Operação da cozinha sem login**, conforme determinação do usuário em 27/10/2026:
  substitui a exigência anterior de perfil para esta tela. Preparar, marcar pronto, cancelar
  com motivo, reimprimir filipeta e gerar etiquetas funcionam diretamente na intranet.
  Rotas `/api/cozinha` e canal `/ws/cozinha-publica/{id}` independem da sessão pessoal;
  resumo operacional filtrado e reconciliação/ETag/WebSocket preservados. Etapas e unidade
  continuam validadas; etiquetas somente em Pronto; envio incerto exige conferência.
  Etapas são auditadas como “Painel da cozinha (sem login)”, sem atribuir conta pessoal.
  Entregas continuam pelo login da copeira; gestão, relatórios e administração protegidos.
  Sem migração de banco. Ver [COZINHA-SEM-LOGIN.md](COZINHA-SEM-LOGIN.md).
  238 testes backend e 56 frontend aprovados; 5 externos omitidos. Build aprovado,
  dois avisos de lint anteriores. Conferência visual sem login de preparo, conclusão,
  prévia de etiqueta, cancelamento e sincronização simultânea entre duas telas.

- ✅ **Cozinha, relatório e formulários** ajustados em 26/10/2026:
  Cancelar abre uma caixa de motivo obrigatório (5–1.000 caracteres), também exigido nas
  duas rotas da API. Eventos preservam motivo, conta autenticada e horário do servidor;
  o relatório distingue solicitante de cancelador e exporta esses dados em XLSX/ODS/CSV.
  A Nutrição mantém textos, cardápios e opções das listas; a edição da estrutura dos campos
  entre o aviso e o cardápio, inclusão/remoção e restauração ficam disponíveis à TI,
  com proteção na API. Líquido espessado usa Sim/Não e lista condicional obrigatória em Sim;
  Não limpa a seleção. A lista anterior continua configurável pela Nutrição e os valores
  anteriores permanecem legíveis. Sem migração ou alteração de pedidos já registrados.
  Validados 225 testes de backend e 54 de frontend, com 5 testes externos omitidos;
  impressão revalidada em 13 testes após atualizar a expectativa para Sim + líquido.
  Build aprovado, dois avisos de lint preexistentes. Conferência visual isolada de
  cancelamento, relatório, publicação pela Nutrição e seleção condicional.

- ✅ **Histórico de alterações** restrito ao perfil **ADMIN_TI** em 26/10/2026:
  aba e conteúdo ocultos para gestores de Nutrição; consulta da API recusa todos
  os demais perfis (403) e acesso anônimo (401). Ações continuam auditadas e os
  registros existentes são preservados. Sem migração de banco ou mudança de senha.
  24 testes direcionados aprovados em SQLite/PostgreSQL isolados, build e
  conferência visual dos perfis Nutrição/TI. Lint mantém os dois avisos anteriores.

- ✅ Gestão de Nutrição: aba redundante **Refeições médicas** removida em 26/10/2026.
  A configuração permanece concentrada em **Formulários → Médico**, incluindo
  refeições, suco, sobremesa e local de entrega. Componente sem uso removido;
  nenhuma alteração de API, banco ou opções cadastradas.

- ✅ Melhorias **1–4 de rastreabilidade assistencial** aplicadas em 26/10/2026:
  referência da prescrição vigente obrigatória para paciente/ambos; nomes digitados
  explicitamente informados, separados da conta autenticada; Gestão/Administração
  com **Prescrições e rastreabilidade**, conferência manual, correção com motivo,
  versões e autor/horário. Correção invalida conferência, volta a Pendentes e
  substitui impressões pendentes; documentos enviados/incertos exigem confirmação
  de substituição com a cozinha. Eventos preservam nomes/perfis à época; histórico
  JSON e relatório Excel/ODS/CSV com metadados da prescrição. Dados anteriores
  sem prescrição/autores presumidos. Consulta pública somente por número/etapa;
  detalhes operacionais e nomes de copeiras exigem conta/vínculo, inclusive em
  HTTP/WebSocket, com limpeza ao sair. Campos clínicos completos só Gestão/TI.
  Migração aditiva de duas colunas e uma tabela. 188 testes de backend e 31 de
  frontend aprovados; cinco testes opcionais de infraestrutura dispensados nesta
  rodada, build e conferência desktop/mobile com dados fictícios. Lint conserva
  os dois avisos anteriores. Publicado na rede, saúde/prontidão HTTP 200 e acesso
  assistencial anônimo HTTP 401. Backup anterior privado, SHA-256 dos campos
  existentes das 17 tabelas preservado na migração; tabela de eventos vazia,
  sem prescrições retroativas. Recuperação real posterior validou as 18 tabelas
  e removeu a cópia temporária. Veja [fluxo e limites](PRESCRICOES-E-RASTREABILIDADE.md).

- ✅ Melhorias **1 e 6 da lista de 23/10** aplicadas em 26/10/2026: Administração
  abre em **Monitoramento**, com API, banco, atividade/contadores da fila e resultado
  da recuperação, atualizado a cada 15 segundos. Detalhes somente ADMIN_TI; sonda
  pública mínima `/api/health/ready` consulta o banco e retorna 200/503, preservando
  `/api/health` como liveness. Consumidor mantém sinal de atividade; Docker verifica
  prontidão. CLI `backend/validar_recuperacao.py --container dietas-db` cria backup
  privado consistente e restaura em banco UUID separado, sem API/seed/impressão.
  Recuperação real validada nas **17 tabelas**, incluindo conteúdo SHA-256, estrutura,
  sequências, formulários, pedidos e PNGs de assinaturas; cópia temporária removida.
  Resultado privado em `work/recuperacao/ultimo_resultado.json`, somente resumo
  permitido na API; dumps e dados fora do Git. Compose monta somente esse diretório
  de relatório como leitura. Validação: 178 testes de backend e 28 de frontend
  aprovados, um teste opcional de HTTPS dispensado, build e conferência desktop/mobile.
  Lint mantém os dois avisos anteriores. Integridade das 17 tabelas preservada na
  publicação; saúde/prontidão HTTP 200 na rede. Veja
  [MONITORAMENTO-E-RECUPERACAO.md](MONITORAMENTO-E-RECUPERACAO.md).

- ✅ Melhorias **2–5 da lista sugerida em 23/10** aplicadas em 26/10/2026:
  **Central de impressões** na Gestão/TI, com filtros/paginação e reenvio protegido
  pela fila existente; **pesquisa e filtros** de andar, leito, formulário e refeição
  na cozinha/entregas, recolhíveis no celular; **Alertas de demora** com padrão de
  **30 minutos por etapa** (solicitação → pronto e pronto → entrega), editáveis e
  desativáveis por unidade; **Histórico de alterações** com autor, data e valores
  anteriores/novos de cadastros, formulários/cardápios, credenciais, impressoras e
  prazos. Auditoria na mesma transação, sem senhas/hashes/tokens ou eventos antigos
  presumidos; credenciais somente para TI. Gravação de formulários serializada
  para preservar versões e histórico sob concorrência.
  Validação: 166 testes de backend aprovados (um teste opcional de HTTPS dispensado),
  25 de frontend, build e conferência desktop/mobile com dados fictícios. Lint mantém
  os dois avisos anteriores de efeitos. Banco temporário para testes PostgreSQL,
  sem impressão física. Backup anterior privado com catálogo legível, integridade
  das 14 tabelas existentes confirmada, duas tabelas novas e índice da fila criados.
  Instalação atual respondendo HTTP 200 na rede; contas e senhas preservadas.
  Detalhes e permissões em [MELHORIAS-OPERACIONAIS-2-5.md](MELHORIAS-OPERACIONAIS-2-5.md).

- ⏳ HTTPS preparado em 23/10/2026, **ainda não ativado**: aguardando o nome DNS
  reservado à aplicação e os arquivos do certificado/chave da TI. Solicitados ao
  usuário; não foram encontrados nas pastas consultadas ou no repositório pessoal
  de certificados. Não presumir que o domínio do AD é o endereço do aplicativo.
  `configurar-https.ps1` prepara PEM/PFX, valida SAN/validade/chave/uso, testa
  confiança TLS em sonda local antes da troca e permite aplicar com reversão.
  `start.ps1` mantém HTTP por padrão e suporta Caddy com frontend compilado quando
  existe `work/https/active.json`. Caddy 2.11.7 obtido da distribuição oficial,
  pacote SHA-256 conferido; certificados/chaves/binários fora do Git. Portas 80 e
  5173 passam a redirecionar para HTTPS/443 somente após aplicação. API e banco
  preservados; nenhum certificado de teste foi instalado no Windows.
  Sete testes de HTTPS aprovados, incluindo gateway real local com CA descartável,
  redirecionamento canônico/caminho/parâmetros, SPA, API, WSS e falhas TLS; nginx -t
  e Compose HTTPS conferidos em contêiner temporário sem portas públicas ou dados
  do hospital. Scripts PowerShell conferidos; start em HTTP e acesso da rede
  responderam HTTP 200. Homologação do certificado real, DNS, firewall e confiança
  nas outras máquinas permanece pendente. Veja [HTTPS.md](HTTPS.md).

- ✅ Integração opcional com AD local preparada em 23/10/2026. Administração →
  Credenciais permite conta local ou vínculo AD (UPN), mantendo perfil e unidades
  no Cnutri. Somente contas previamente cadastradas/ativas acessam; senha da rede
  não é persistida, não há fallback local, certificados LDAPS são obrigatórios e
  login AD exige HTTPS. GUID fixa a identidade após o primeiro login; mantém um
  administrador local ativo e revoga sessões ao converter origem/identidade.
  Sessão AD limitada a 30 minutos por padrão; situação no domínio é reavaliada
  no login, sem consulta contínua ao AD. Ver [configuração e limites](ACTIVE-DIRECTORY.md).
  Domínio informado salvo somente no ambiente privado; AD permanece desativado,
  aguardando a TI indicar controlador/certificados e a publicação HTTPS futura.
  Descoberta DNS local encontrou vários controladores, sem escolher um ou enviar
  credenciais. Nenhuma conta existente convertida. Passaram 138 testes de backend
  (incluindo nove PostgreSQL em banco temporário separado) e 19 de frontend, além
  de build e conferência do cadastro/edição em navegador com dados fictícios.
  Lint mantém os dois avisos anteriores em Gestao.jsx. Atualização disponível na
  rede, HTTP 200, integridade dos dados anteriores nas 14 tabelas confirmada;
  backup privado `backups/backup-dietas-2026-10-23-antes-ad.dump` com catálogo de
  124 linhas legível, sem teste completo de restauração.

- ✅ Editor de formulários da Gestão identificado em 22/10/2026: nome de cada campo
  acima da caixa de opções, incluindo listas e botões de seleção, com atualização
  automática ao renomear ou criar campos. Nome/tipo do campo, título, informativo e
  grupos de cardápio também têm rótulos visíveis e associados aos controles.
  Conferido no navegador com dados fictícios nos formulários de paciente e médico,
  inclusive em tela de celular de 390 × 844; build aprovado e lint somente com os
  dois avisos anteriores de dependências de useEffect. Alteração visual, sem mudança
  nos esquemas, opções ou dados já publicados.

- ✅ Cabeçalho de todas as etiquetas ajustado em 22/10/2026: somente o nome da
  unidade em negrito e fonte fixa de 11 pontos, sem o prefixo “Unidade:”, nos modelos de paciente,
  acompanhante e profissional.
  Os 23 testes de etiquetas passaram, incluindo cabeçalho fixo em 203/300 dpi e
  quebra de nomes longos sem sobreposição; prévia fictícia conferida,
  atualização ativa na rede e integridade das 14 tabelas preservada.

- ✅ Etiqueta do formulário médico habilitada em Prontos (22/10/2026), inclusive para
  a equipe Administração. Uma etiqueta de 89 × 36 mm com unidade, profissional,
  registro profissional, equipe/horário, refeição, suco/sobremesa e local de entrega,
  além de marca d'água e rodapé CONSUMO IMEDIATO. Nome do solicitante identifica o
  destinatário; não exige dados de paciente. Mesma impressora/fila da unidade.
  APIs mantêm perfil, vínculo, nome obrigatório correspondente ao formulário e
  status Pronto. Pedidos de paciente continuam exigindo o nome do paciente.
  Prévia e enfileiramento médico conferidos no navegador com dados fictícios;
  112 testes de backend, 17 de frontend e build aprovados. Lint mantém os dois
  avisos anteriores de dependências de useEffect em Gestao.jsx.
  Atualização ativa na rede, HTTP 200, integridade das 14 tabelas confirmada e
  backup local `backups/backup-dietas-2026-10-22-antes-etiqueta-medico.dump`
  com catálogo legível, fora do Git; conferência física da impressão pendente.

- ✅ Condições do campo Para no formulário de paciente (22/10/2026): Paciente mantém
  o fluxo; Acompanhante permite somente dieta GERAL e seu grupo de cardápio;
  Paciente e Acompanhante mantém a dieta/cardápio do paciente e exige o novo
  **Cardápio do acompanhante**, logo abaixo, com opções do grupo GERAL.
  Campo adicional derivado do cadastro vigente da Gestão, sem duplicar listas
  ou alterar o esquema salvo. Regras também no servidor; trocas limpam opções
  incompatíveis e retiram o campo oculto do envio. GERAL inativa ou sem cardápio
  bloqueia solicitações com acompanhante e orienta procurar a Nutrição.
  Valor em `dados_dinamicos.cardapio_acompanhante`, exibido na cozinha/entregas,
  filipeta e relatórios/exportações. Sem migração de banco ou divisão de pedidos;
  histórico e resumo por solicitações preservados. Conferência no navegador com
  dados fictícios e regressões em SQLite/PostgreSQL isolados.
  Validação mais recente: 101 testes de backend, 17 de frontend e build aprovados;
  lint com os dois avisos anteriores de dependências de useEffect em Gestao.jsx.
  Atualização ativa na rede, com HTTP 200 e o campo derivado conferido na API.
  Integridade das 14 tabelas confirmada após reinício; backup local anterior em
  `backups/backup-dietas-2026-10-22-antes-acompanhante.dump` (catálogo legível,
  sem teste de restauração completo), fora do Git.

- ✅ Etiquetas de 89 mm × 36 mm atualizadas em 22/10/2026: unidade, matrícula, nome,
  data de nascimento (dia/mês/ano), dieta cadastrada, andar e leito, nessa ordem.
  Acompanhante: dieta GERAL e identificação **Acompanhante** à direita na linha do
  leito. Paciente e Acompanhante: um clique prepara/envia duas etiquetas distintas,
  uma de cada tipo; prévias individuais, inclusive no celular, e quantidade
  explícita no botão. Um trabalho contém os dois documentos, sem duplicar cliques;
  falha de preparação impede envio parcial e transmissão incerta exige conferir
  o papel antes de repetir o conjunto completo. Nenhuma mudança de banco.
  Rodapé **CONSUMO IMEDIATO** e ícone do navegador como marca d'água pontilhada,
  compatível com a impressão monocromática em 203 e 300 dpi, com prévia dos mesmos pixels.
  Cadastro por unidade em Administração → Impressoras, com modelo/IP/porta/ZPL ou TSPL/dpi.
  Botão e prévia na cozinha somente em Prontos, com autorização e conferência do status também
  no servidor/consumidor. Fila independente da filipeta, acentos rasterizados e reenvio controlado.
  Nenhum IP de etiquetas ativado automaticamente; usuário ainda não possui os modelos/IPs.
  Validação mais recente: 108 testes de backend, 17 de frontend e build aprovados.
  Etiquetas individuais e par conferidos no navegador com dados fictícios, incluindo
  tela mobile de 390 × 844. Atualização na rede com HTTP 200, 14 tabelas preservadas
  e backup local `backups/backup-dietas-2026-10-22-antes-etiquetas-acompanhante.dump`.
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
4. **Cozinha e entregas:** pesquisa e filtros implementados em 26/10/2026;
   reorganizar as colunas por refeição continua sendo uma opção futura.
5. **Produção / item 10:** adiado pelo usuário para outro servidor; já há domínio e certificado
   da TI. Retomar HTTPS, início/recuperação automáticos, validar prontidão no destino, restrições de rede,
   credencial do banco, backup agendado e CORS_ORIGINS com a URL definitiva nessa instalação.

Os **seis itens da lista de melhorias de 23/10 estão concluídos** na instalação atual:
1 e 6 no documento de monitoramento/recuperação; 2–5 no documento de melhorias
operacionais. A implantação em outro servidor continua como etapa própria.

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
Para criar uma cópia e testar a recuperação em banco temporário separado:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\validar_recuperacao.py --container dietas-db
```

O comando preserva a origem e não inicia a aplicação na cópia. Para manutenção em
outro ambiente e alcance da validação, veja [MONITORAMENTO-E-RECUPERACAO.md](MONITORAMENTO-E-RECUPERACAO.md).

## 8. Fluxo de trabalho (multi-estação)

- Código: `git pull` antes de editar → alterar → testar → `git push` (GitHub: Markyto84/Cnutri)
- Formulários: atualizar a cópia de configuração versionada ao sincronizar alterações feitas no painel
- Dados: em produção, um único banco no servidor central acessado por todos via navegador
- Ao concluir mudanças relevantes, **atualizar este arquivo** (seção 4 e 5)
