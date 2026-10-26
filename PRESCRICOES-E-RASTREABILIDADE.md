# Prescrições e rastreabilidade — 26/10/2026

## Formulário e conferência

O formulário do paciente solicita referência da prescrição/atendimento no prontuário
de origem, data/hora de Brasília, nome do prescritor e conselho, região/UF e registro.
Obrigatório para Paciente e Paciente e Acompanhante. Acompanhante e refeições da
equipe médica/administrativa mantêm o fluxo próprio, sem referência clínica.

A referência começa como **Informada**. Os nomes digitados são declarações do
solicitante. Se houver sessão autenticada vinculada à unidade, a conta que enviou
também é registrada separadamente. O comprovante público devolve somente número
do pedido e estado da filipeta.

Gestão/Administração → **Prescrições e rastreabilidade** permite buscar por número,
paciente ou prontuário, abrir dados e registrar a conferência do vínculo com a
prescrição consultada. O servidor registra usuário, nome e horário. Gestores acessam
as unidades ativas vinculadas à conta; a TI pode consultar qualquer unidade.

## Correções e histórico

**Corrigir pedido** usa o formulário vigente, exige motivo e preserva o solicitante
original. Armazena versão anterior/nova, autor, perfil e horário. Requer nova
conferência e devolve a Pendentes para a cozinha preparar a versão atual.

Trabalhos de impressão pendentes ou falhos são cancelados e uma nova filipeta
entra na fila normal. Etiquetas continuam permitidas somente em Pronto. Se já
houve envio ou transmissão incerta, exige confirmação da substituição dos
documentos anteriores com a cozinha, conservando o registro original do envio.
Impressão em andamento bloqueia a correção. Pedidos entregues/cancelados e unidades
inativas mantêm o histórico para consulta. Edições da mesma versão em concorrência
recebem conflito, sem sobrescrita.

Eventos registram solicitação, conferência, correção, mudanças de etapa e entrega.
Novos eventos preservam nome/perfil da conta no momento da ação, mesmo que o
cadastro seja renomeado. A entrega distingue copeira responsável, conta que
registrou e recebedor; a assinatura existente continua como comprovante de entrega.
Etapas antigas conservam os dados disponíveis, com nome atual do cadastro identificado
como tal. Não há autores antigos presumidos.

O histórico completo pode ser baixado em JSON. O relatório de dietas, inclusive
Excel, Calc e CSV, inclui referência, data, prescritor, conferência, responsável,
horário e versão do pedido. Arquivos e histórico exigem Gestão/Administração.

## Permissões e privacidade

| Acesso | Dados |
|---|---|
| Sem login | Número, unidade, tipo, etapa e horários; sem nomes, dietas, alergias ou localização |
| Cozinha/Copeira vinculadas | Dados necessários ao preparo/entrega; listas e canais sem prontuário, matrícula, nascimento ou referência da prescrição |
| Nutrição vinculada / Administração | Dados assistenciais, conferência, correção e histórico da unidade autorizada |

As impressões já autorizadas à cozinha conservam os campos necessários às
etiquetas/filipetas. A referência da prescrição permanece na Gestão, sem ser
adicionada à etiqueta. A lista nominal de copeiras também exige sessão da unidade.
HTTP/WebSocket usam projeções explícitas; novos campos não passam automaticamente
ao acesso público. Respostas da API usam `Cache-Control: private, no-store`.
Sair da sessão remove imediatamente detalhes e diálogos do painel.

## Migração e limites

Migração aditiva: `pedidos.prescricao` começa nulo e `pedidos.versao` em 1.
A tabela `eventos_assistenciais` guarda novos eventos, sem rotas para editá-los
ou apagá-los. Pedidos anteriores ficam **Sem referência registrada**; nenhuma
prescrição ou conferência é criada retroativamente.

O Cnutri registra referência externa e evidências do fluxo de refeições.
Não emite nem assina a prescrição clínica: autenticidade, vigência e assinatura
profissional permanecem no prontuário de origem. A conferência é manual, sem
integração automática. O responsável pelo serviço valida o protocolo assistencial.

## Validação

188 testes de backend aprovados, incluindo PostgreSQL temporário, migração
idempotente, duas correções simultâneas, permissões HTTP/WebSocket e substituição
de documentos. Cinco testes opcionais de infraestrutura (Caddy e recuperação com
contêiner explícito) não executados nesta rodada. 31 testes de frontend e build
aprovados. Lint conserva os dois avisos de efeitos já existentes em Gestão.

Navegador conferido com dados fictícios: referência, conferência, correção,
histórico, modo público após logout e tela de 390 × 844. Homologação isolada,
sem impressoras e sem dados de pacientes reais.

Publicação na rede concluída com backup privado anterior e conferência SHA-256
dos campos existentes das 17 tabelas, preservados antes de reiniciar os serviços.
A tabela nova iniciou vazia, sem atribuições retroativas. API/prontidão HTTP 200,
área assistencial sem sessão HTTP 401 e projeção pública conferida sem campos
clínicos. Recuperação real após a atualização validou as 18 tabelas, conteúdo,
estrutura e sequências, em banco temporário separado, removido ao final; sem
iniciar API ou impressão da cópia. Senhas e configurações anteriores preservadas.
