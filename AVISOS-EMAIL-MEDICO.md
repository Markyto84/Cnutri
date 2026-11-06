# Avisos de saída das refeições médicas

O formulário Médico / Administração pede o e-mail na identificação do solicitante.
Ao avançar de **Em preparo** para **Pronto**, a mesma transação grava a mudança
e o aviso. Essa é a etapa que representa a saída para entrega neste fluxo.

O e-mail tem uma versão em texto e uma ficha HTML adaptável ao celular, com a
paleta do Cnutri, nome do solicitante, unidade, número do pedido e as escolhas
preenchidas: equipe, horário, refeição, cardápio, suco, sobremesa, local e
observações. O conteúdo é congelado ao marcar Pronto e escapado para HTML.
Não há formulário executável, imagens externas, rastreamento de abertura, foto
da filipeta nem código de acesso ao recebimento no e-mail.

## Configurar por unidade

Em **Administração de TI → Avisos por e-mail**, selecione a unidade e escolha:

1. **Google Workspace · Senha de app**: informe o e-mail de dietas da unidade
   e uma senha de app de 16 caracteres. A conta precisa ter verificação em duas
   etapas e a política do Workspace deve permitir esse recurso. O Cnutri usa
   `smtp.gmail.com:587`, STARTTLS, validando o certificado do Google. O endereço
   remetente é também o usuário de autenticação. A senha comum da conta não é
   o método de configuração desse envio automático.
   O painel apresenta o passo a passo e o link direto para
   [Senhas de app do Google](https://myaccount.google.com/apppasswords).
   Gere a credencial na conta de dietas da unidade, cole os 16 caracteres,
   salve a configuração e então teste a conexão.
2. **Google Workspace · Relay autorizado pela TI**: informe o remetente da
   unidade. A TI autoriza previamente o IP público de saída do servidor e os
   remetentes no console do Google. O Cnutri usa `smtp-relay.gmail.com:587` com
   STARTTLS, sem armazenar senha nesse modo.

Salve e use **Testar conexão**. O teste faz a conexão segura e, no modo senha
de app, autentica. Ele não envia mensagem. No relay, a autorização do remetente
e do destinatário só é conferida durante um envio real. Após a homologação da
TI, ative os avisos da unidade. Nenhuma unidade é ativada automaticamente.

Referências oficiais consultadas em 06/11/2026:
- [Google: envio por aplicativos e configurações SMTP](https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app?hl=en).
- [Google: senhas de app e requisitos da conta](https://support.google.com/accounts/answer/185833?hl=pt-BR).
- [Google: configuração do SMTP relay](https://knowledge.workspace.google.com/admin/gmail/advanced/route-outgoing-smtp-relay-messages-through-google?hl=en).

## Credenciais e instalação

A senha de app é cifrada com Fernet, vinculada à unidade e nunca devolvida
pela API, gravada em auditoria ou incluída em mensagens de erro do provedor.
Somente ADMIN_TI pode configurar, testar e acompanhar os avisos.

Para cadastrar ou substituir a senha, use HTTPS ou acesse o Cnutri pelo
endereço de loopback na própria máquina do servidor. Os acessos HTTP da rede
podem consultar o painel autenticado, mas não cadastrar credenciais.

O assistente `backend/configurar_ambiente.py` prepara automaticamente a chave
`EMAIL_CREDENCIAIS_CHAVE` no `.env` privado do backend para a instalação local.
O assistente `backend/configurar_servidor.py` faz o mesmo em instalações Linux
novas; em uma instalação existente, execute-o com `--preparar-email` e
`--diretorio` apontando para a instalação. Essa opção adiciona somente a chave,
preservando os demais dados. O Compose encaminha a chave ao backend. Reinicie a API após preparar a
chave pela primeira vez. Assistentes preservam uma chave existente.

**Inclua o arquivo privado de configuração na recuperação da instalação**, em
armazenamento restrito e separado do dump. Sem a chave original será necessário
recadastrar as senhas de app. O dump contém somente as credenciais cifradas.
As chaves e senhas não entram em fontes, Git, instaladores ou exemplos públicos.
Não troque a chave isoladamente enquanto houver senhas cadastradas.

## Fila e falhas

- A requisição da cozinha apenas grava o aviso. Um consumidor separado transmite
  os e-mails; falhas no Google não desfazem o preparo nem afetam a impressão.
- Há unicidade por pedido/versão. Repetir o clique em Pronto não cria outro aviso.
- Falhas de conexão anteriores ao envio e recusas temporárias têm até três
  tentativas, com espera crescente. O erro exibido é uma descrição controlada.
- Queda depois de iniciar a transmissão e processamento interrompido ficam como
  **Precisa de conferência**, sem reenvio automático. SMTP não garante que um
  aceite perdido possa ser distinguido de uma mensagem não recebida; por isso
  um reenvio incerto exige conferência humana.
- Antes de transmitir, a fila confere unidade ativa, pedido Pronto, versão e
  validade. Uma alteração depois dessa conferência, com a transmissão já em
  andamento, não pode retirar um e-mail já entregue ao servidor SMTP.
- Avisos de saída são válidos por 30 minutos após Pronto. Pedidos já entregues,
  cancelados, substituídos ou com aviso expirado não geram mensagens atrasadas.
- **Aceito pelo servidor de e-mail** confirma a aceitação SMTP; não confirma
  chegada à caixa de entrada, leitura nem ausência de filtros ou devoluções.
- Se o envio estava desativado ao marcar Pronto, isso fica registrado. A ativação
  posterior não dispara esse histórico automaticamente. A TI pode tentar um
  aviso explicitamente enquanto o pedido e a janela de envio ainda forem válidos.

O e-mail fica em tabela própria de contato e não aparece nos canais públicos
da cozinha, na confirmação pública de envio, na filipeta ou nas etiquetas.
Pedidos antigos sem contato continuam avançando normalmente; formulários de
Enfermagem / Paciente mantêm o fluxo atual. As três tabelas novas são aditivas.

## Homologação

Use um pedido fictício e uma conta destinatária de teste autorizada pela TI:

1. Cadastre o remetente da unidade e confira o teste de conexão.
2. Solicite a refeição com o e-mail de teste.
3. Confira que Em preparo não envia e-mail; avance para Pronto.
4. Confira a ficha recebida, acentos, local e resumo no computador e celular.
5. Repita o clique e confira apenas um aviso na fila.
6. Confira que a conta de outra unidade não é utilizada.

Os testes automatizados isolam bancos, credenciais e transporte. Eles não
enviam mensagens ao Google nem criam pedidos na operação real. A chegada na
caixa de entrada depende da homologação com a conta e as regras da empresa.
