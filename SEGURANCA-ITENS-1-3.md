# Cnutri — melhorias 1 a 3 do review

Implementação de 20/10/2026. A atualização preserva pedidos, formulários, impressoras e contas existentes.

## 1. Credenciais e autenticação

- O segredo JWT não tem valor padrão. A instalação Windows gera `backend/.env` com valores aleatórios e ACL restrita ao usuário do Windows e ao SYSTEM. O arquivo fica fora do Git e fora dos diretórios servidos pelo Vite.
- `atualizar_seguranca.py` substitui somente a senha inicial pública das versões antigas. Cada conta recebe uma senha temporária diferente, em arquivo privado local. Senhas personalizadas são preservadas. O comando pode ser repetido sem redefinir novamente as contas já atualizadas.
- O primeiro acesso com senha criada/redefinida pela TI permite consultar a própria conta, trocar a senha ou sair. Operações e presença de plantão ficam bloqueadas até a troca.
- Login, troca e redefinição bloqueiam a linha da conta durante a operação para respeitar redefinições concorrentes. Por solicitação do usuário em 20/10/2026, senhas novas exigem de 8 a 12 caracteres, com pelo menos uma letra maiúscula, um número e um caractere especial. O gerador de temporárias usa 12 caracteres. Senhas já existentes continuam válidas até serem alteradas. Cada usuário pode alterar a própria senha em `/senha`, informando a atual. A TI redefine a senha de outras contas pelo painel.
- A mudança do segredo invalida tokens anteriores. Sessões passam a ser persistidas para todos os perfis, com validade, encerramento no logout e revogação na troca/reset de senha.
- Cinco falhas de autenticação por usuário/IP em 15 minutos bloqueiam novas tentativas até o fim da janela. Há limite geral de 100 falhas por IP. A troca de senha também limita erros de senha atual. Contadores persistidos funcionam entre processos e reinícios; respostas limitadas incluem `Retry-After`.
- Logs registram falhas, limitação e identificador do usuário quando conhecido, sem senhas ou tokens. O cadastro de usuário inexistente não é revelado pela resposta do login.
- Produção exige segredo JWT exclusivo com pelo menos 32 caracteres e senha de banco com pelo menos 12 caracteres; recusa valores padrão e contas com a antiga senha pública. Em banco vazio, cria somente o administrador com a senha inicial privada configurada.

### Atualizar uma instalação Windows antiga

1. Faça backup do PostgreSQL.
2. Execute `backend\.venv\Scripts\python.exe backend\configurar_ambiente.py --inicializar-admin`.
3. Execute `backend\.venv\Scripts\python.exe backend\atualizar_seguranca.py`.
4. Entregue os acessos do arquivo privado informado à TI e reinicie com `stop.ps1` e `start.ps1`.
5. Acesse `/login` e defina uma nova senha. Não compartilhe o arquivo por chat nem o versione.

A variável `ADMIN_INICIAL_SENHA` serve somente para o administrador de um banco vazio. Ela não é a senha das contas rotacionadas de uma instalação existente.

## 2. Ações operacionais autorizadas

| Ação | Sem login | Cozinha | Copeira | Nutricionista | Admin TI |
|---|---|---|---|---|---|
| Consultar dashboard e entregas de unidade ativa | Sim | Sim | Sim | Sim | Sim |
| Enviar formulário público validado | Sim | Sim | Sim | Sim | Sim |
| Iniciar preparo, marcar pronto, cancelar, reimprimir | Não | Na própria unidade | Não | Na própria unidade | Todas as unidades ativas |
| Registrar entrega com recebedor e assinatura | Não | Não | Somente em seu nome | Por copeira online da unidade | Por copeira online da unidade |
| Consultar relatórios e assinatura | Não | Não | Não | Na própria unidade | Todas as unidades |

“Própria unidade” significa vínculo com unidade ativa no cadastro. Senha temporária ainda não trocada não autoriza operações.

As telas públicas mostram o acesso ao login; os botões aparecem conforme as permissões. A API aplica as mesmas regras independentemente da tela. Depois do login, o usuário retorna ao painel permitido; destinos externos e unidades sem vínculo são descartados.

O histórico de status/reimpressão recebe o operador autenticado. A entrega guarda a copeira responsável e o usuário que a registrou. Ambos aparecem nos relatórios e exportações XLSX/ODS/CSV. Entregas anteriores mantêm seus dados e mostram operador não registrado, sem presumir quem executou a ação.

## 3. Pedidos validados pelo formulário atual

Antes de gravar ou imprimir, o servidor carrega o formulário vigente da unidade e do fluxo Médico/Enfermagem e verifica:

- Solicitante e registro profissional preenchidos, sem aceitar somente espaços.
- Campos obrigatórios, inclusive textos longos; tipos dos valores; datas válidas e nascimento até hoje.
- Opções exatas de listas e rádios, inclusive refeição, equipe, horário, suco, sobremesa e local.
- Dieta ativa da unidade e cardápio pertencente ao grupo da dieta selecionada. Quando não há grupo/opções configurados para a dieta, o cardápio segue desabilitado e dispensado, como na tela existente.
- Limites: leito 30, prontuário/registro 50, nome 100, texto dinâmico 1.000, opções 2.000 e observações/texto longo 5.000 caracteres; até 100 campos e 64 KB no JSON dinâmico.
- Ausência de campos dinâmicos desconhecidos ou duplicações dos campos fixos. Configurações publicadas pela gestão são conferidas quanto a identificadores, tipos, opções e obrigatoriedade.

Solicitações inválidas recebem HTTP 422 com o campo e o motivo; nenhum pedido ou impressão é gerado. Sem formulário configurado, a resposta é HTTP 409. Um formulário antigo aberto no navegador precisa respeitar as opções atuais ao enviar. Pedidos antigos não são alterados retroativamente.

O frontend usa `required` também em texto longo, associa rótulos aos controles e aplica limites de preenchimento. O payload separa campos fixos e dinâmicos, sem duplicação.

## Validação e continuidade

Testes automatizados cobrem autorização por perfil/unidade, atribuição da entrega, senha temporária, revogação de sessões, tentativas de autenticação, rotação idempotente e validação dos formulários. São 59 testes do backend, incluindo a migração PostgreSQL em schema temporário com rollback e dois testes de redefinição concorrente de senha em schemas exclusivos removidos ao final; os testes funcionais usam SQLite e dados fictícios. Não há impressão física nos testes.

Execute no backend: `python -m unittest discover -s tests -v` (dependências de teste: `httpx` e `aiosqlite`). Para incluir a migração, configure `CNUTRI_TEST_POSTGRES_URL` para um PostgreSQL de teste. No frontend: `npm test` (quatro testes), `npm run build`, `npm run lint`. A compilação passou; o lint mantém dois avisos anteriores de dependências de efeitos em `Gestao.jsx`.

As sessões foram incluídas para garantir a segurança da troca de credenciais. Continuam no plano do review: fila e confirmação de impressão, proteção contra envio repetido, correções dos relatórios de turno/agrupamento, comunicação entre workers e instalação de produção com HTTPS, supervisão e backups. O Windows atual usa um worker; o pacote de produção ainda requer a etapa de comunicação entre workers para fechar canais em todos os processos.
