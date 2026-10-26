# Melhorias operacionais 2–5 — 26/10/2026

Implementação dos itens da lista sugerida em **23/10/2026**, posterior ao review
de segurança de 20/10. Disponível na instalação atual e nas telas para celular.

## 2. Central de impressões

Na Gestão e na Administração, abra **Central de impressões**. A lista reúne os
trabalhos de filipetas e etiquetas, com filtros de unidade, situação, documento,
número do pedido e período. Usa paginação, ordenação pelos trabalhos mais recentes
e atualização a cada 15 segundos. O período inicial é de sete dias; a consulta aceita
até 91 dias por vez, sem limitar o histórico armazenado a esse período.

O último trabalho com falha ou envio incerto pode ser reenviado enquanto o pedido
estiver em operação. Envios incertos exigem a conferência explícita do papel.
Etiquetas permanecem restritas a **PRONTO**. O reenvio utiliza a mesma fila durável;
não executa impressão dentro da requisição. Outro painel ou clique repetido não
cria um segundo reenvio do mesmo trabalho. Trabalhos anteriores continuam visíveis.
“Enviado” significa transmissão TCP, sem comprovar saída física do papel.

A TI consulta todas as unidades. Gestão e Cozinha só consultam/operam unidades
permitidas. A API não retorna o conteúdo dos documentos, configurações internas da
fila, prontuário ou dados de paciente nessa central. Copeiras e visitantes não têm
acesso à central. Permissões também são verificadas no reenvio.

## 3. Pesquisa e filtros operacionais

**Cozinha** e **Entregas** oferecem busca por número de pedido, nome ou leito e
filtros combinados de andar/setor, leito, tipo de formulário e refeição. A pesquisa
ignora diferenças de acentuação e maiúsculas. Limpar filtros restaura a listagem.
As contagens das etapas acompanham os resultados filtrados; a consulta de entregas
permanece limitada a refeições prontas. Os eventos em tempo real e os alertas sonoros
de novos pedidos continuam recebidos mesmo quando há um filtro aplicado.

No celular, **Mostrar filtros** expande os campos. Os controles são rotulados e
recolhíveis para manter espaço para as refeições. Opções de filtros são obtidas
dos pedidos em operação, sem alterar as listas configuradas dos formulários.

## 4. Prazos configuráveis

Por escolha do usuário, o padrão de cada unidade é:

| Etapa | Prazo inicial | Início da contagem |
| --- | --- | --- |
| Solicitação até refeição pronta | 30 minutos | Data/hora da solicitação |
| Refeição pronta até entrega | 30 minutos | Data/hora em que foi marcada pronta |

Na Gestão ou Administração, abra **Alertas de demora** para editar os minutos ou
desativar cada etapa separadamente. Valores aceitos: de 1 a 1.440 minutos. Sem uma
configuração específica, vale o padrão de 30 minutos; um valor nulo explicitamente
salvo desativa o alerta. Novas unidades também começam com esse padrão.

Os cartões exibem o tempo decorrido e o limite quando o prazo é atingido. Pedidos
entregues/cancelados não geram alerta. Uma refeição pronta antiga sem horário de
conclusão não recebe um tempo de entrega presumido. Os prazos não mudam estados
automaticamente. A configuração chega aos painéis na atualização periódica de dez
segundos; o relógio visual também se atualiza sem depender de eventos WebSocket.

## 5. Histórico administrativo

Na Gestão ou Administração, abra **Histórico de alterações** para consultar autor,
data/hora, cadastro afetado e os valores anteriores/novos. Há filtros de unidade,
tipo de cadastro e período, além de paginação.

São registrados cadastros e alterações de unidades, dietas, formulários/cardápios,
credenciais/perfis/vínculos, impressoras e prazos. Copiar uma nova unidade registra
também os formulários e dietas criados. Troca/reset de senha registra somente o
evento, sem a senha. Não são armazenados hashes, tokens, cookies ou conteúdo de
pedidos nessa auditoria. Credenciais são visíveis exclusivamente à TI; a Gestão
consulta apenas alterações das unidades permitidas.

O evento é gravado na mesma transação da alteração. Uma falha/rollback não deixa
histórico de uma mudança inexistente. Salvar sem modificar valores não inventa uma
alteração. Publicações de formulário também serializam a verificação da versão e
a gravação, rejeitando uma edição simultânea com versão antiga.

O histórico começa nesta atualização. Não foram fabricados registros retroativos.
Não há rota de edição ou remoção dos eventos.

## Aplicação e validação

- Backend: **166 testes aprovados**, em 167 casos descobertos. O teste opcional de
  gateway real Caddy/HTTPS foi dispensado por não estar habilitado nesta execução.
  Foram incluídas regressões de autorização, privacidade, estados de impressão,
  padrões/desativação dos alertas, atomicidade da auditoria e concorrência em
  PostgreSQL temporário, separado dos dados operacionais.
- Frontend: **25 testes aprovados**, build aprovado e lint sem erros; permanecem os
  dois avisos anteriores de dependências de efeitos em `Gestao.jsx`.
- Conferência em navegador com banco em memória e dados fictícios: central,
  filtros combinados, confirmação/reenvio simulado, edição de prazos e comparação
  antes/depois no histórico. Revisão desktop e em largura de 390 pixels. Nenhuma
  impressão física de teste foi enviada.
- Backup privado anterior em `backups/backup-dietas-2026-10-26-antes-melhorias-2-5.dump`;
  catálogo legível. Não substitui o teste completo de restauração do item 6.
- Inicialização cria `configuracoes_operacionais`, `auditoria_administrativa` e o
  índice de data/ID da fila, sem reescrever os registros anteriores. Comparação por
  contagem e resumo criptográfico confirmou a preservação das **14 tabelas** já
  existentes, incluindo contas, senhas, pedidos, assinaturas e documentos.
- API, formulário e prazos responderam por localhost e pelo endereço da rede
  `http://10.1.140.15:5173`. Central e auditoria recusaram acesso anônimo (HTTP 401).

Esta etapa não inclui os itens 1 (monitoramento de API/banco) e 6 (recuperação
completa de backups) da lista de 23/10, nem muda a preparação de HTTPS/AD.
