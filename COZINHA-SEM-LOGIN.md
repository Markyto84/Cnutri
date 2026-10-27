# Cozinha sem login — 27/10/2026

A operação da cozinha na intranet dispensa credenciais, conforme solicitado pelo usuário.
Em `/cozinha/{nome-da-unidade}` é possível consultar dados de preparo, iniciar preparo, marcar pronto,
cancelar com motivo, reimprimir filipeta e visualizar/imprimir etiquetas.

## Endereços por unidade

As URLs usam o identificador já cadastrado (`codigo_slug`): `/cozinha/unidade-havai`,
`/cozinha/unidade-colorado` e `/cozinha/unidade-dubai`. Links anteriores como `/cozinha/1`
redirecionam para o nome da unidade. Gestão, administração, entregas e seletor geram os nomes.
O snapshot `/api/cozinha/unidades/{referencia}/estado` e o canal
`/ws/cozinha-publica/{referencia}` resolvem tanto o nome quanto IDs anteriores. As ações
continuam usando internamente o ID real, preservando a associação entre unidade e pedido.
IDs, nomes cadastrados, dados e regras de acesso são preservados.

## Acesso e dados

O cliente da cozinha usa `/api/cozinha` sem enviar a credencial pessoal. A sessão de
gestão ou plantão, inclusive expirada ou com senha temporária, não condiciona as ações
desta tela. O canal `/ws/cozinha-publica/{id}` mantém atualizações ao vivo e o HTTP
reconcilia a cada aproximadamente dois minutos com ETag, conforme a política dos painéis.

O snapshot e o canal transmitem somente o resumo operacional: destinatário, dieta,
cardápios, restrições, local, idade, etapa e estado de impressão. Prontuário, matrícula,
nascimento completo, prescrição, assinatura e cadastro de copeiras ficam fora desse resumo.
A prévia/impressão da etiqueta preserva os campos próprios do documento solicitado.

## Regras de operação e histórico

- O servidor valida unidade ativa e pertencimento do pedido à unidade.
- As etapas seguem Pendentes → Em preparo → Prontos. Cancelamento exige motivo de 5 a 1.000 caracteres.
- Pedidos entregues/cancelados não avançam. Atualizações concorrentes preservam uma única alteração.
- Etiquetas exigem Pronto. A fila mantém idempotência e exige confirmação para repetir um envio incerto.
- Etapas são registradas como **Painel da cozinha (sem login)**, perfil técnico `COZINHA_PUBLICA`,
  sem ID de usuário. Motivo e horário do servidor aparecem no relatório/exportações; o solicitante
  original do pedido é preservado. Trabalhos de impressão não são atribuídos a uma conta pessoal.

A conclusão da entrega continua identificada pelo login da copeira. Gestão, administração,
relatórios, credenciais e configuração de impressoras continuam exigindo os respectivos acessos.
As rotas anteriores em `/api/operacao` e `/api/pedidos` mantêm suas permissões.

## Validação

238 testes backend e 56 frontend aprovados; cinco testes externos dependentes de infraestrutura
foram omitidos. Inclui operação anônima, credencial inválida, motivos, relatório, concorrência
PostgreSQL, fila simulada, etiqueta, isolamento de unidade e canais. Build aprovado; lint com
dois avisos preexistentes. Teste visual isolado de preparo/conclusão, prévia de etiqueta e
cancelamento, com atualização simultânea de duas telas sem login. Nenhum pedido real foi
usado nos testes e nenhuma impressora física recebeu testes nesta alteração. Sem migração de banco.
