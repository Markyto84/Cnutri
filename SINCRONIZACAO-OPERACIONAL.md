# Sincronização dos painéis de Cozinha e Entregas

Implementação de 26/10/2026. Mantém os dados em tempo real com redução de consultas,
reconciliação periódica e recuperação de falhas. Não exige migração de tabelas.

## Funcionamento

- O WebSocket continua transmitindo criação, etapas, correções e estado das impressões.
- Uma única consulta a `/api/operacao/unidades/{id}/estado` reúne pedidos ativos,
  unidades, prazos e copeiras online. Substitui as três consultas de 10 segundos e
  a consulta de copeiras de 5 segundos.
- Com WebSocket conectado, a conferência HTTP acontece aproximadamente a cada
  **dois minutos**, com variação de 10% para distribuir as chamadas entre os aparelhos.
- O ETag identifica o conteúdo por unidade/usuário. Se nada mudou, a API responde
  **304 sem corpo**. A autorização e a validade da sessão continuam sendo verificadas.
- Unidades, prazos e plantão são conferidos por um monitor central no servidor,
  a cada **5 segundos**, somente quando há painéis conectados. São três consultas
  compartilhadas por ciclo, independentemente da quantidade de telas.
- Esse monitor publica apenas mudanças. Nomes de copeiras são enviados somente
  a canais autenticados; pedidos públicos continuam limitados a número e etapa.
- O heartbeat de presença das copeiras permanece em **30 segundos**, com expiração
  de 3 minutos, preservando a regra atual de disponibilidade para entrega.

## Falhas e retomada

- Sem WebSocket, mas com API disponível, Entregas consulta a cada **5 segundos**;
  Cozinha, a cada **10 segundos**, também com pequena variação nos intervalos.
- Se a API também falhar, o intervalo aumenta progressivamente até **60 segundos**.
- O WebSocket tenta reconectar com espera progressiva, limitada a **30 segundos**.
- Pulso de aplicação a cada **25 segundos** detecta uma conexão aparentemente
  aberta que parou de responder. Uma tela visível reconecta após aproximadamente
  60–75 segundos sem mensagens; em segundo plano, a tolerância é maior.
- Ao recuperar a conexão, voltar ao primeiro plano ou recuperar a rede, a tela
  confere o estado atual. Uma chamada em andamento é compartilhada, sem criar
  consultas paralelas para a mesma tela.
- Telas ocultas mantêm eventos e suspendem conferências HTTP de rotina enquanto
  o canal está conectado. Ao voltar, fazem uma nova conferência.
- Eventos recebidos durante uma consulta são reaplicados depois da resposta,
  impedindo que um HTTP antigo ressuscite uma entrega ou apague um pedido novo.
- Se a conexão for aberta depois do início de uma consulta, outra conferência
  fecha a janela em que eventos poderiam ter sido perdidos.
- Revogação, falta de permissão e unidade indisponível limpam os dados restritos e
  encerram as tentativas automáticas. O botão Atualizar permite uma nova autorização.
- Trocar de unidade/conta desmonta a sincronização anterior, cancela a consulta e
  descarta os dados. Pedidos e listas não são persistidos no navegador; apenas o
  ETag da tela atual fica temporariamente em memória. As respostas usam `no-store`.

## Impacto estimado nas 21 unidades

Referência: 1 computador em Cozinha, 5 celulares e 2 tablets em Entregas por unidade,
todos ativos 24h, cinco presenças de copeira por unidade, conexão estável.

| Chamadas HTTP de rotina/dia | Antes | Depois |
|---|---:|---:|
| Unidades, pedidos, prazos e copeiras | 6.894.720 | aproximadamente 120.960 |
| Presença das copeiras | 302.400 | 302.400 |
| **Total** | **7.197.120** | **aproximadamente 423.360** |

Redução estimada: **94,1%** no total de chamadas HTTP de rotina e **98,2%** nas
consultas dos painéis. Não são 94% de redução garantida em bytes: respostas 200/304,
quantidade de pedidos, mensagens WebSocket e uso dos aparelhos influenciam a banda.
Criação, assinatura, impressão, cliques manuais, reconexões e logins não entram
nessa contagem de rotina. O número real inclui as conferências iniciais.

## Validação

- Testes com relógio virtual simulam 24 horas e verificam uma consulta inicial e
  720 reconciliações por tela; também cobrem quedas, reconexão, retorno à tela,
  resposta 304, eventos durante HTTP lento, revogação e desmontagem.
- Testes de API e monitor em SQLite e PostgreSQL verificam autorização antes de
  304, separação público/privado, alteração de prazos, expiração de presença e
  três consultas centrais para múltiplas telas/unidades.
- Regressão do backend: 204 testes aprovados; cinco testes de gateway HTTPS e
  recuperação dependem de ambientes adicionais e não foram executados nesta rodada.
- Build do frontend e lint aprovados; permanecem dois avisos anteriores em Gestao.jsx.
- Homologação no navegador usa somente dados fictícios e impressoras desativadas.

## Publicação e limites

Publicar primeiro o backend, que mantém as rotas anteriores, e depois o frontend.
Telas antigas continuam funcionando até carregar a nova versão. O processo da API
é reiniciado para ativar o monitor e as novas rotas; não é necessário alterar dados.

Permanece obrigatório **um worker de API**, pois o gerenciador de WebSocket é local
ao processo. Para múltiplos processos/servidores, é necessário um barramento de
eventos compartilhado antes de ampliar essa configuração. A reconciliação HTTP
recupera divergências, mas não substitui esse barramento para entrega imediata.

O teste funcional não substitui homologação de carga dos 168 acessos no futuro
servidor ou medição dos enlaces de todas as unidades.
