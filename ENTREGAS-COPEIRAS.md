# Identificação da copeira no celular pelo QR Code

## Operação

1. A cozinha segue com acesso direto e prepara a refeição normalmente.
2. Ao entregar a refeição, a copeira escaneia o **QR Code da filipeta no celular**. Na primeira leitura sem sessão válida, a página solicita login nesse dispositivo.
3. Após autenticar, a página retorna à mesma refeição e o servidor registra o ID e o nome da copeira da sessão, com data e hora. Nas próximas leituras, a sessão ativa é reutilizada. Não há retirada obrigatória nem pedido de login pelo painel da cozinha ou de entregas.
4. No celular, são informados o nome e o registro profissional do recebedor. **Confirmar recebimento** registra o horário e marca **Entregue**. O login pertence à copeira que opera o dispositivo; o recebedor é identificado pelos campos do formulário.
5. Os relatórios de entregas e de dietas exibem a copeira, o horário de sua identificação e o recebimento. XLSX, ODS e CSV têm os mesmos dados.

A autenticação continua usando as contas locais ou o AD já configurado. Não há criação de senhas, redefinição de credenciais ou alteração das condições de uso do AD nesta mudança.

## Consistência e compatibilidade

`retiradas_pedidos` conserva o vínculo por pedido e versão, com nome preservado, operador e horário do banco. O campo técnico `retirada_em` permanece compatível e é apresentado como **Identificação da copeira**: a leitura ocorre no momento da entrega e não comprova uma retirada física anterior da cozinha. Os registros anteriores não são alterados.

A identificação mantém o estado de preparo `PRONTO` no banco. **Em entrega** indica que a copeira já foi identificada no QR Code e o recebimento está pendente. A mudança para `ENTREGUE` pertence à confirmação do recebimento.

Identificação e confirmação bloqueiam a mesma linha de pedido no PostgreSQL. Releituras da mesma copeira preservam o vínculo e o horário; outra conta não pode assumir nem confirmar o pedido. As duas ações exigem sessão válida, perfil **COPEIRA** e acesso à unidade. Uma sessão encerrada ou expirada exige novo login no celular, mantendo o vínculo já registrado. A presença é atualizada enquanto a página de recebimento está aberta.

O retorno após login guarda o código opaco em `sessionStorage` da aba. A URL de login contém somente `retorno=/receber`, sem o código da filipeta. Após o login — inclusive troca obrigatória de senha — o código retorna ao fragmento `#` da URL de recebimento. O formulário não aceita destinos externos como retorno. O logout limpa o código guardado e as intenções do fluxo anterior.

O painel passou a orientar a leitura do QR Code, sem botão de retirada ou redirecionamento para login. A rota anterior de retirada fica compatível com registros e clientes anteriores, sem ser usada pelo fluxo atual. A identificação pelo QR Code não aceita nome de copeira, ID de outro usuário ou horário fornecido pelo cliente. A autoria é auditada como `COPEIRA_IDENTIFICADA_QR` e a conclusão como `ENTREGA_CONFIRMADA_QR`.

Filipetas antigas sem QR Code mantêm o encerramento manual para operadores autenticados. Recebimentos anteriores não recebem identificação retroativa presumida. Consultar um QR Code concluído continua mostrando seu comprovante, sem registrar uma nova entrega nem exigir novo login.

## Validação em 28/10/2026

- Suíte geral do backend, com bancos fictícios: concluída sem falhas; os testes condicionais sem ambiente disponível foram explicitamente ignorados.
- Testes adicionais em PostgreSQL 16 descartável: duas leituras simultâneas por copeiras distintas, repetição de leituras, autorização por unidade e perfil, rejeição de identidade ou horário forjados, sessão encerrada e confirmação pelo QR Code.
- Exportações XLSX, ODS e CSV: identificação e horários separados, com células de data reais nas planilhas.
- Frontend: testes, lint e compilação. Permanecem apenas os dois avisos anteriores de dependências de efeitos em `Gestao.jsx`.
- Navegador do chat com aplicação e banco fictício: leitura do primeiro QR Code solicitou login no dispositivo e retornou à refeição; leitura seguinte reutilizou a sessão, sem passagem pelo painel da cozinha.

Não foram usados pacientes, credenciais ou impressoras reais na homologação. Logs, capturas e contas fictícias ficam sob `work/`, fora do versionamento. Antes da atualização do ambiente em uso, é preservado um backup do PostgreSQL.
