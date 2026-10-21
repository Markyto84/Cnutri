# Estabilização — itens 4 a 9 do review

Atualização aplicada em 20/10/2026. O item 10 foi adiado a pedido do usuário para a
instalação em outro servidor, com domínio e certificado da TI. HTTPS, inicialização
automática, supervisão e alterações de rede/credencial do banco não foram ativados
nesta etapa. O acesso atual continua em `http://10.1.140.15:5173`.

## Sessões e canais internos — item 4

Todos os perfis usam sessões persistidas. Logout revoga a sessão atual; troca ou
redefinição de senha revoga as sessões anteriores. Esses eventos fecham os canais
internos do usuário. A conexão privada também verifica sessão, perfil e unidade a
cada 30 segundos, inclusive quando o cliente não envia mensagens ou envia mensagens
continuamente. Expiração da sessão é detectada nessa verificação. Os dashboards
públicos continuam disponíveis para consulta.

## Fila de impressão — item 5

Pedido e trabalho de impressão são gravados na mesma transação. O processamento
ocorre em segundo plano; desenho da filipeta e envio TCP executam fora do loop da
API. A fila fica na tabela `trabalhos_impressao`, com estados visíveis no cartão da
cozinha e na confirmação da solicitação:

| Estado | Comportamento |
|---|---|
| PENDENTE | Aguardando envio; impede outro trabalho ativo para o pedido. |
| PROCESSANDO | Trabalho reservado pelo consumidor da fila. |
| ENVIADO | Dados enviados por TCP; não confirma a saída física do papel. |
| FALHA | Sem impressora, sem conexão após as tentativas ou falha de preparação. |
| INCERTO | Transmissão interrompida ou processamento abandonado; exige conferir o papel antes de reenviar. |
| CANCELADO | Pedido cancelado antes de processar o trabalho; não envia a filipeta. |

Falhas antes de estabelecer conexão permitem até três tentativas no total, com
intervalos de 15 e 30 segundos. O documento gerado é preservado nas tentativas.
Falhas depois de conectar não são reenviadas automaticamente, pois parte do papel
pode ter sido impressa. Trabalhos PROCESSANDO há mais de 60 segundos passam a
INCERTO. Após reiniciar a API, trabalhos pendentes continuam na fila persistida.

**Reenviar filipeta** e **Reimprimir** exigem operador autorizado. No estado INCERTO,
a tela pede conferência do papel e a API exige confirmação explícita. Repetir o
clique enquanto existe trabalho ativo retorna esse mesmo trabalho. A rota retorna
HTTP 202 com `enfileirado` e `impressao`; não executa TCP dentro da requisição.

Pedidos anteriores à atualização ficam sem registro de impressão na nova fila.
Não são enfileirados automaticamente. A filipeta conserva fonte de 10 pontos,
acentos rasterizados, campos configurados e rodapé de assinatura/data, omitindo
Sexo e Prontuário conforme solicitado anteriormente.

## Repetição de solicitações — item 6

O kiosk gera uma chave UUID aleatória por tentativa e a envia no cabeçalho
`Idempotency-Key`. O banco impõe unicidade por unidade/chave. Repetir o mesmo
conteúdo retorna HTTP 200 com o pedido original, sem criar pedido, impressão ou
evento de novo pedido. Outro conteúdo com a mesma chave retorna HTTP 409 e informa
o número original; os novos dados não são enviados. Chaves diferentes permitem
solicitações legítimas iguais.

A chave é mantida no `sessionStorage` até concluir a tentativa; nomes e dados do
formulário não são guardados nesse armazenamento. Recarregar a página pode recuperar
o número e o estado de impressão por essa chave, sem expor dados pessoais na rota
de consulta. Se o armazenamento estiver bloqueado, a chave permanece em memória
enquanto a página estiver aberta. **Nova solicitação** inicia outra tentativa; após
20 segundos na confirmação, o kiosk também volta ao início.

Clientes antigos sem o cabeçalho continuam compatíveis, mas precisam adotá-lo para
obter proteção contra repetição. O kiosk atualizado já o utiliza no link HTTP da rede.

## Relatórios — itens 7 e 8

O consumo médico converte UTC para Brasília antes de classificar os turnos:
Manhã das 06h às 11h59, Tarde das 12h às 17h59 e Noite nos demais horários.

O resumo de dietas agrupa por IDs da unidade e da dieta/categoria. Nomes iguais
continuam em grupos separados, inclusive dentro da mesma unidade. A tela identifica
as unidades pelo código; XLSX, ODS e CSV incluem código/ID da unidade e ID da dieta
nas colunas finais, preservando as colunas anteriores.

## Processo da API — item 9

O Dockerfile agora fixa `--workers 1`. O Windows atual já usa um único processo.
Os eventos WebSocket e o fechamento dos canais permanecem no mesmo processo da API.
Não aumentar workers nem replicar a API antes de implantar transporte compartilhado
de eventos e revogações. Não foi realizado teste de carga distribuído.

## Validação e aplicação

- 76 testes de backend aprovados: 70 isolados em SQLite/Python e seis em schemas
  PostgreSQL exclusivos, sem acessar registros operacionais. Incluem concorrência
  de envio/consumo da fila, migração legada, revogação de canais, falhas de impressão,
  fuso e unidades/dietas homônimas.
- Oito testes de frontend, build e lint aprovados. Lint mantém dois avisos anteriores
  de dependências de efeitos em `Gestao.jsx`.
- Conferência no navegador com dados fictícios: confirmação com número, recuperação
  do mesmo número após recarregar, avisos da fila, bloqueio de reenvio pendente e
  confirmação de transmissão incerta em computador e largura de 390 pixels.
- Backup anterior: `backups/backup-dietas-2026-10-20-antes-itens-4-9.dump`, fora do Git;
  leitura do catálogo validada com `pg_restore --list`. Não equivale a teste de restauração.
- Migração aditiva aplicada. Conferência antes/depois confirmou a preservação de
  cadastros, senhas, formulários, pedidos, histórico, entregas, assinaturas e sessões.
  Nenhum pedido antigo foi enfileirado.
- API e frontend reiniciados; saúde e formulário responderam HTTP 200 por localhost
  e pelo IP de rede da estação. Nenhuma impressão de teste foi enviada ao equipamento
  real nesta etapa; transmissão e falhas foram simuladas nos testes.

Ao atualizar outras instalações, faça backup, pare a API antiga, atualize o código
e reinicie com um único worker. A inicialização cria a tabela da fila e acrescenta
as colunas/índice de idempotência sem reescrever os pedidos anteriores. Preserve o
banco e os arquivos privados de ambiente; um `git pull` não transfere esses dados.
