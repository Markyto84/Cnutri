# Entrega direta — assinatura suspensa

Na tela de Entregas, a copeira logada finaliza cada refeição pronta pelo botão
**Realizar entrega**. Não abre formulário de assinatura, não informa recebedor e
não precisa selecionar o próprio nome. A mensagem de sucesso confirma que o
atendimento foi finalizado.

O servidor identifica a copeira pela sessão autenticada, verifica vínculo com a
unidade e presença no plantão e exige que a refeição ainda esteja PRONTO. Na mesma
transação registra responsável, usuário da ação, data/hora do banco e histórico,
e altera o pedido para ENTREGUE. A refeição sai dos painéis ativos via WebSocket.

Cliques repetidos são bloqueados na tela durante o envio. A atualização condicional
do banco também impede duas finalizações simultâneas. Uma copeira não pode declarar
a identidade de outra na requisição. Gestão/TI continua precisando selecionar uma
copeira online e confirmar em **Finalizar atendimento**.

## Registros e relatórios

- Entregas do novo fluxo não criam linha em `recebimentos_entregas`, não inventam
  recebedor e não geram imagem vazia. O evento de entrega registra
  `assinatura_registrada: false`.
- O relatório mantém copeira, operador e data/hora da entrega; informa quando não
  há assinatura. Somente registros com recebedor mostram esse campo.
- Os comprovantes anteriores são preservados e continuam acessíveis aos perfis
  de gestão/TI autorizados. Não há migração ou exclusão de dados.
- A captura não é importada pela página atual. O código do módulo de assinatura
  está preservado para uma possível reativação futura.

## Compatibilidade

`POST /api/operacao/unidades/{unidade}/pedidos/{pedido}/entregar` aceita corpo vazio
ou `{}` para Copeira; a identidade vem da sessão. Gestão/TI envia `copeira_id`.

Clientes anteriores ainda podem enviar nome e assinatura completos enquanto
carregam a nova versão. O servidor continua validando esses comprovantes e não
aceita apenas um dos dois campos. As permissões de consulta de assinaturas e
relatórios continuam sendo verificadas no servidor.

## Verificação

Testes conferem finalização sem assinatura, identidade da sessão, presença na
unidade, bloqueio de outra identidade e falta de login, registro no relatório,
histórico e ausência de comprovante artificial. PostgreSQL verifica que duas
requisições concorrentes produzem uma entrega e um conflito, sem duplicação.
Os testes de comprovantes anteriores e do módulo preservado continuam aplicáveis.

Validação de 26/10/2026: 213 testes de backend e 51 de frontend aprovados, além
do build. Cinco testes de HTTPS/recuperação dependentes de ambientes específicos
ficaram fora desta rodada. A entrega direta foi concluída no navegador com dados
fictícios, e o relatório confirmou copeira, horário e ausência de assinatura.
