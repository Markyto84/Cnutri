# Retirada pela copeira e confirmação de recebimento

## Operação

1. A cozinha segue com acesso direto e prepara a refeição normalmente.
2. No painel de entregas, **Retirar para entrega** solicita login quando não há sessão válida. Após autenticar, a ação escolhida continua na unidade autorizada. Nas retiradas seguintes, a sessão existente é utilizada.
3. O servidor registra o ID e o nome da copeira e a data e hora da retirada. O painel identifica **Em entrega** e aguarda o recebedor.
4. O recebedor abre o QR Code da filipeta, visualiza a copeira responsável, informa seu nome e registro profissional e confirma. A confirmação registra o horário de recebimento e marca **Entregue**.
5. Os relatórios de entregas e de dietas exibem a copeira e os horários separados. XLSX, ODS e CSV incluem a retirada e a etapa da entrega.

A autenticação continua usando as contas locais ou o AD já configurado. Não há criação de senhas, redefinição de credenciais ou alteração das condições de uso do AD nesta mudança.

## Consistência e compatibilidade

`retiradas_pedidos` guarda uma retirada por pedido e versão, com nome preservado, operador e horário do banco. É uma tabela adicional criada na inicialização pela rotina existente `Base.metadata.create_all`; não há atualização dos pedidos ou recebimentos antigos.

A retirada mantém o estado de preparo `PRONTO` no banco. A etapa de transporte **Em entrega** é derivada de sua retirada, preservando as integrações, a impressão de etiquetas e o cálculo do prazo entre preparo e recebimento. A mudança para `ENTREGUE` continua pertencendo à confirmação pelo QR Code.

As retiradas e confirmações bloqueiam a mesma linha de pedido no PostgreSQL. Repetir a retirada da mesma copeira retorna o registro existente; outra copeira recebe conflito. A versão enviada pelo painel é conferida para impedir ações sobre uma refeição corrigida. Os registros de versões anteriores permanecem no histórico. A presença é exigida ao retirar; sair do plantão posteriormente não apaga o vínculo nem impede o recebimento.

O retorno após login usa uma intenção de retirada em `sessionStorage`, restrita à aba, unidade e prazo de cinco minutos. Ela é consumida uma vez e apagada no logout. Não há execução de ações a partir de parâmetros arbitrários da URL. O login, a troca obrigatória de senha e os vínculos de unidade conservam suas verificações existentes.

Gestão e Administração podem indicar uma copeira online da unidade, com autoria da ação registrada. A confirmação por QR Code não aceita data, nome da copeira ou operador fornecidos pelo cliente. No painel público de entregas, somente a indicação de etapa é divulgada; os nomes e demais dados continuam restritos ao acesso autorizado. A consulta pelo código opaco da filipeta mostra apenas o resumo de recebimento e a copeira responsável.

Filipetas antigas sem QR Code mantêm o encerramento manual já existente. Recebimentos anteriores não recebem identificação retroativa presumida. Nas filipetas com QR Code ainda não confirmadas, a retirada deve ser registrada antes da confirmação do recebedor.

## Validação em 28/10/2026

- Suíte geral do backend, com bancos fictícios: concluída sem falhas; os testes condicionais sem ambiente disponível foram explicitamente ignorados.
- Testes adicionais em PostgreSQL 16 descartável: duas copeiras simultâneas, reenvios simultâneos, autorização por unidade, identidade própria, presença, histórico de versões, saída do plantão e confirmação por QR Code.
- Exportações XLSX, ODS e CSV: identificação e horários separados, com células de data reais nas planilhas.
- Frontend: testes, lint e compilação. Permanecem apenas os dois avisos anteriores de dependências de efeitos em `Gestao.jsx`.
- Navegador do chat com a aplicação real e banco fictício: primeira retirada solicitou login e continuou após autenticar; a segunda não repetiu login; o recebedor confirmou pelo QR Code após a copeira sair do plantão.

Não foram usados pacientes, credenciais ou impressoras reais na homologação. Logs, capturas e contas fictícias ficam sob `work/`, fora do versionamento. Antes da atualização do ambiente em uso, é preservado um backup do PostgreSQL.
