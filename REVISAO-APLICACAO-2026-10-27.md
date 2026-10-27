# Revisão do Cnutri — 27/10/2026

Versão examinada: `1b9a834`. Revisão de código, testes automatizados e sondagens com dados
fictícios em PostgreSQL temporário. Na aplicação em uso, foram realizadas somente leituras.
Nenhuma correção funcional foi aplicada nesta revisão.

## Atualização — correções dos itens 4–5

Os itens **1–5 estão corrigidos**. Os itens **6–7 continuam pendentes**.
As evidências originais abaixo descrevem a versão anterior às correções.

- **Códigos das unidades:** criação e edição recusam endereços sem letras e nomes reservados
  pela aplicação/proxy, como `login`, `admin`, `cozinha`, `api` e `ws`. A TI recebe uma mensagem
  clara sem perder o formulário preenchido. O backend também rejeita chamadas diretas inválidas
  antes de gravar unidade, formulários ou histórico. Cadastros antigos continuam consultáveis
  pela TI para correção; não há alteração automática de códigos, nomes, IDs ou pedidos.
- **Compatibilidade do proxy:** os prefixos `/api` e `/ws` só encaminham suas próprias rotas.
  Nomes válidos como `api-hospital` e `ws-sul` podem abrir o formulário normalmente. Os
  cabeçalhos de protocolo e as conexões WebSocket mantêm suas proteções anteriores.
- **Acesso por unidade (ajustado após orientação do usuário):** distribuem-se atalhos com
  as URLs específicas dos formulários e cozinhas. A página de seleção foi removida, junto
  da consulta de unidades e do redirecionamento automático. `/` apenas orienta a usar o
  atalho fornecido pela TI. Os endereços atuais de cada unidade foram preservados.
- **Endereços inválidos e falhas:** caminhos desconhecidos e unidades inexistentes orientam
  a conferir o endereço do atalho com o suporte. Falhas de conexão oferecem nova tentativa. A troca entre
  unidades reinicia o formulário, evitando mostrar dados do endereço anterior.

Conferência da versão intermediária no navegador com dados fictícios: seleção com três unidades, redirecionamento
com uma, estado sem unidades, código numérico bloqueado pelo navegador, mensagem do backend
para `login`, formulário/cozinha por nome, caminhos inexistentes e recuperação após interromper
e reiniciar somente a API de homologação. A página inicial foi conferida em desktop e celular
de 390 px. Evidências locais em `work/validacao-4-5/`.

Validação da versão intermediária do lote 4–5: **260 testes de backend e 68 de frontend aprovados (328 no total)**;
5 verificações externas de Caddy/restauração omitidas. Build aprovado; lint com somente
os dois avisos preexistentes em `Gestao.jsx`. Logs: `work-revisao-4-5-completo.log`,
`work-revisao-4-5-direcionados.log` e `work-revisao-4-5-frontend.log`.

Ajuste final solicitado pelo usuário: validação dos códigos e compatibilidade dos links
mantidas; seleção de unidades removida. A mudança é somente no frontend e na documentação.
Os 67 testes restantes do frontend e o build passaram; lint com os dois avisos anteriores.
No navegador de homologação, o endereço principal permanece neutro mesmo com uma unidade
ativa; os links específicos abrem diretamente o formulário e a cozinha sem login.

## Atualização — correções dos itens 1–3

Os itens **1–3 foram corrigidos** após a revisão. As evidências originais abaixo se referem
à versão `1b9a834`, anterior a essas correções. O lote seguinte dos itens 4–5 está descrito acima.

- **Formulários públicos:** configuração, envio e consulta do comprovante usam um cliente HTTP
  próprio, sem anexar a sessão pessoal ou redirecionar ao login. A identificação do solicitante,
  os campos obrigatórios e a chave de idempotência são preservados. O cliente das áreas
  autenticadas e as regras de autenticação do backend permanecem vigentes.
- **Etapas:** as rotas antiga, autenticada e pública da cozinha compartilham a mesma regra.
  Pedidos seguem `PENDENTE → EM_PREPARO → PRONTO`; podem ser cancelados com motivo enquanto
  ativos. Cancelados e entregues não podem ser reabertos por essas rotas. Histórico e controle
  de atualizações simultâneas são preservados; a cozinha continua funcionando sem login.
- **Filipetas:** pedidos cancelados não geram novas reimpressões. A fila relê e bloqueia o
  pedido imediatamente antes da transmissão, inclusive quando reutiliza um documento já
  preparado. Cancelamento confirmado antes desse ponto impede o envio. Se a transmissão já
  começou, o cancelamento aguarda sua conclusão ou timeout; um documento já transmitido
  permanece registrado como enviado. Envios parciais continuam exigindo conferência antes
  de uma nova tentativa, evitando reimpressão automática incerta.

Regressões cobrem a matriz de etapas das três rotas, perfil/unidade, cancelamento durante
a preparação e as duas ordens de concorrência entre transmissão e cancelamento em PostgreSQL.
Uma verificação HTTP isolada dos formulários Médico e Enfermagem confirmou os três cenários
de sessão (ausente, expirada e de outra unidade), validação dos campos, repetição idempotente,
conflito de dados e recuperação do comprovante. Impressão foi simulada, sem impressoras reais.

Validação após as correções: **252 testes de backend e 65 de frontend aprovados (317 no total)**;
5 verificações externas de Caddy/restauração omitidas. Build aprovado; lint manteve somente
os dois avisos anteriores em `Gestao.jsx`. Logs locais: `work-revisao-correcoes-completo.log`,
`work-revisao-correcoes-frontend.log` e `work-revisao-correcoes-http.log`.

O critério de operação permanece: **cozinha sem login**, solicitante informado nos formulários,
entrega identificada pelo login da copeira e acessos próprios para gestão e administração.

## Resultado e ordem sugerida

| Ordem | Prioridade | Classificação | Trabalho recomendado |
|---|---|---|---|
| 1 | Alta | Erro confirmado | Separar o envio dos formulários públicos da sessão pessoal do navegador. |
| 2 | Alta | Erro confirmado | Aplicar a mesma validação de etapas também à rota antiga de pedidos. |
| 3 | Alta | Erro confirmado | Revalidar cancelamento da filipeta antes da transmissão à impressora. |
| 4 | Média | Erro confirmado | Impedir códigos de unidade numéricos ou conflitantes com rotas da aplicação. |
| 5 | Média | Erro de entrada confirmado | Substituir a unidade padrão inexistente da página inicial por uma entrada válida. |
| 6 | Média, antes de ampliar o uso | Melhoria de desempenho | Exportar períodos grandes em lotes ou em tarefa de segundo plano. |
| 7 | Antes da migração de servidor | Melhoria de manutenção | Fixar as versões Python testadas para tornar a instalação reproduzível. |

Os itens 1–5 são problemas funcionais identificados; os itens 6–7 são melhorias preventivas.
Sugestão: executar primeiro **1–3**, depois **4–5**, e preparar **6–7** para a ampliação e migração.

## 1. Formulário público pode ser bloqueado pela sessão pessoal

**Evidência:** o mesmo pedido fictício recebeu `201` sem token, `401` com token inválido
e `403` com sessão válida vinculada a outra unidade. O formulário usa o cliente HTTP que
anexa automaticamente a credencial pessoal. O backend público tenta validar essa credencial
e o cliente redireciona para `/login` ao receber `401`.

**Impacto:** um posto compartilhado pode deixar de enviar a solicitação pública porque alguém
usou uma conta de gestão/copeira no mesmo navegador. Uma sessão expirada pode levar ao login
e à perda do formulário preenchido. Não é necessário que exista erro na senha informada pelo solicitante.

**Correção proposta:** utilizar um cliente próprio para as chamadas públicas do quiosque,
independente do token pessoal, seguindo o padrão já empregado na cozinha. Preservar os campos
de solicitante, a validação do formulário e a proteção contra envio duplicado. Manter intactos
os controles das rotas autenticadas.

**Aceite:** enviar Médico e Enfermagem sem sessão, com token expirado e com sessão de outra unidade;
os três cenários devem manter o fluxo público e os mesmos controles de validação/idempotência.

Fontes: [Kiosk.jsx](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/frontend/src/pages/Kiosk.jsx:78>),
[api.js](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/frontend/src/services/api.js:7>) e
[public_kiosk.py](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/app/api/public_kiosk.py:63>).

## 2. A rota antiga permite reabrir cancelamentos e pular etapas

**Evidência:** chamadas autenticadas à rota `/api/pedidos/{id}/status` aceitaram
`CANCELADO → PRONTO` e `PENDENTE → PRONTO`, ambas com retorno `200`. Essa rota bloqueia
pedidos entregues, mas não aplica a mesma sequência de etapas da cozinha atual.

**Impacto:** clientes antigos ou chamadas diretas com uma conta autorizada podem reativar
uma refeição cancelada ou concluir o preparo sem passar pela etapa anterior. O painel atual
tem validação mais restrita; as duas entradas da aplicação ficam inconsistentes.

**Correção proposta:** compartilhar uma única regra de transições entre as rotas atuais
e a antiga. Preservar cancelamento com motivo, histórico, validação da unidade e controle
de atualizações simultâneas. Uma eventual reabertura precisa de fluxo explícito e motivo.

**Aceite:** ambas as rotas recusam salto de etapa e reabertura de cancelados/entregues,
mantendo a sequência Pendentes → Em preparo → Prontos.

Fonte: [pedidos.py](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/app/api/pedidos.py:63>).

## 3. Cancelamento durante a preparação da filipeta pode chegar depois da última validação

**Evidência:** em uma sondagem controlada, o pedido foi cancelado depois da leitura inicial
da fila e antes da chamada de transporte. Ainda assim, o transporte simulado foi chamado uma
vez e o trabalho terminou como `ENVIADO`, enquanto o pedido já estava `CANCELADO`.
Nenhuma impressora física foi acionada.

**Impacto:** em uma janela de concorrência, pode sair uma filipeta para uma solicitação que
já teve o cancelamento aceito pelo servidor. O código das etiquetas já possui uma segunda
verificação com bloqueio do pedido durante a transmissão; o caminho das filipetas não a possui.

**Correção proposta:** revalidar o pedido imediatamente antes do envio da filipeta e coordenar
esse trecho com o cancelamento. Encerrar trabalhos ainda não enviados quando o pedido deixar
de ser válido. Diferenciar um documento já transmitido de um trabalho que ainda pode ser suspenso.

**Aceite:** cancelamento confirmado antes da transmissão impede a chamada ao transporte.
Testar a concorrência em PostgreSQL e preservar o tratamento de envios incertos, evitando cópias duplicadas.

Fonte: [fila_impressao.py](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/app/services/fila_impressao.py:112>).

## 4. O cadastro aceita códigos de unidade que conflitam com os endereços

**Evidências:**

- Foi cadastrada uma unidade fictícia de ID `3` com código `2`. A URL gerada usava `/cozinha/2`,
  que resolveu a unidade de ID `2`, e não a recém-criada, por causa da compatibilidade com URLs antigas.
- O cadastro também aceitou `login`. O formulário dessa unidade teria endereço `/login`,
  reservado à autenticação pelo roteamento do frontend.

**Impacto:** um novo cadastro ou edição da TI pode produzir um link incorreto ou inacessível.
Os códigos atuais `unidade-havai`, `unidade-colorado` e `unidade-dubai` não apresentam esses conflitos.

**Correção proposta:** validar códigos na criação e na edição, recusando os compostos somente
por números e os reservados pelo roteador/proxy. Manter a unicidade e a compatibilidade com
os links numéricos existentes. A validação deve acontecer no backend, com mensagem clara na interface.

**Aceite:** códigos conflitantes são rejeitados antes de salvar; novos nomes válidos continuam
resolvendo exatamente a unidade cadastrada, sem alterar IDs ou dados de outras unidades.

Fontes: [schemas.py](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/app/schemas/schemas.py:20>),
[cozinha.py](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/app/api/cozinha.py:19>) e
[App.jsx](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/frontend/src/App.jsx:15>).

## 5. A página inicial usa uma unidade inexistente no ambiente atual

**Evidência:** a rota inicial/fallback entrega o quiosque com `unidade-centro` como padrão.
A consulta de leitura `/api/public/unidade-centro/config` retornou `404` no ambiente em uso.

**Impacto:** abrir apenas o endereço principal, sem o caminho de uma unidade, leva ao erro
de unidade indisponível. Os endereços específicos cadastrados continuam funcionando.

**Correção proposta:** criar uma entrada que liste as unidades ativas, com acesso aos formulários
e cozinhas correspondentes. Caso exista apenas uma unidade ativa, permitir redirecionamento
automático para ela. Rotas desconhecidas devem apresentar uma página de endereço não encontrado.

**Aceite:** `/` funciona com uma, várias ou nenhuma unidade ativa e não escolhe uma unidade
inexistente ou arbitrária.

Fonte: [App.jsx](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/frontend/src/App.jsx:22>).

## 6. Exportações grandes acumulam todos os pedidos na memória

**Constatação de código:** a exportação consulta todos os resultados com `.all()`, cria uma
segunda lista com os detalhes e mantém o arquivo produzido em memória até devolver a resposta.
Não há limite de volume ou geração por tarefa. A tela paginada do relatório não tem esse mesmo problema.

**Impacto projetado:** na referência informada de 21 unidades × 100 solicitações/dia,
um ano representa aproximadamente **766.500 solicitações**. Uma exportação desse período,
principalmente simultânea a outras, pode consumir memória e tempo consideráveis. Não foi
executado um teste de carga com esse volume e não foi constatada uma falha de exportação nos dados atuais.

**Melhoria proposta:** consultar/processar em lotes; transmitir CSV progressivamente; gerar
planilhas extensas em tarefa de segundo plano, com progresso e controle de volume. Informar
o limite do formato escolhido e preservar o mesmo filtro na tela e no arquivo.

Fonte: [relatorio_dietas.py](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/app/api/relatorio_dietas.py:62>).

## 7. Instalações Python ainda não são totalmente reproduzíveis

**Constatação:** grande parte de `requirements.txt` usa apenas versão mínima, e o Dockerfile
instala diretamente esse arquivo. Uma instalação nova pode resolver versões diferentes das
que foram aprovadas nos testes desta estação.

**Melhoria proposta:** gerar um arquivo de versões fixas a partir do ambiente validado,
incluindo dependências transitivas, e usar esse arquivo na instalação e na imagem de produção.
Atualizações devem passar pelos testes antes da publicação. Acrescentar auditoria de vulnerabilidades
Python ao processo de validação.

Essa recomendação trata de reprodução e manutenção. Não foi demonstrada uma vulnerabilidade
Python nesta revisão; `pip check` verifica compatibilidade de dependências, não vulnerabilidades.

Fontes: [requirements.txt](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/requirements.txt:1>) e
[Dockerfile](<C:/Users/Suporte/.codex/worktrees/rastreabilidade-dietas/Projeto Cnutri/backend/Dockerfile:9>).

## Verificações realizadas e limites

- Backend: **247 testes executados; 242 aprovados e 5 omitidos** por dependerem de infraestrutura
  externa explicitamente indicada para testes de Caddy/restauração em contêiner.
- Frontend: **60 testes aprovados**. Total da suíte existente: **302 aprovados**.
- Cinco sondagens adicionais em PostgreSQL exclusivo confirmaram os defeitos dos itens 1–4.
  Elas documentam os comportamentos incorretos atuais; não significam que esses defeitos foram corrigidos.
- Build aprovado. Lint com os dois avisos preexistentes de dependências de `useEffect` em `Gestao.jsx`.
- `npm audit`, inclusive dependências de desenvolvimento: **0 vulnerabilidades conhecidas reportadas**
  pelo registro na execução desta revisão. `pip check`: nenhuma incompatibilidade de dependências.
  `pip-audit` não está instalado; a auditoria de vulnerabilidades Python permanece pendente.
- API e prontidão do banco responderam `200` nas verificações de leitura.
- Não foram exercitados impressoras físicas, AD real, certificados reais ou restauração de backup
  no servidor definitivo. HTTPS/AD continuam como preparação de infraestrutura já discutida.
- Os testes usaram dados fictícios e bancos temporários, removidos ao final. Não foram cancelados,
  entregues ou impressos pedidos reais. O código funcional e os serviços em uso permaneceram inalterados.

As evidências locais de reprodução estão em `work/review-20261027-resultados.json` e os logs
em `work-review-completo-20261027.log`, `work-review-frontend-20261027.log` e
`work-review-probes-20261027.log` nesta cópia de trabalho. Os scripts de sondagem também
estão em `work/`, fora do código funcional da aplicação.
