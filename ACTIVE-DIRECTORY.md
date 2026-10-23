# Autenticação pelo Active Directory

A TI pode cadastrar uma **conta local** ou um vínculo com o **AD local do Windows
Server** em Administração → Credenciais. O nome de usuário do Cnutri continua
sendo o nome digitado no login. Para contas AD, a senha é a senha da rede.
O perfil e as unidades autorizadas são definidos no Cnutri. Ser usuário do domínio
ou pertencer a um grupo administrativo do Windows não concede acesso ao Cnutri.

A integração vem **desativada**. Os usuários existentes continuam locais, com as
mesmas senhas, perfis, vínculos e sessões. Nenhuma conta é convertida automaticamente.
Prepare os vínculos e ative o AD somente após a TI validar o servidor e o HTTPS.

## Configuração no servidor do Cnutri

Defina estas variáveis no ambiente privado do **backend**, fora do Git. Nomes e
caminhos abaixo são exemplos; substitua pelos dados fornecidos pela TI:

```dotenv
AD_HABILITADO=false
AD_DOMINIO=empresa.local
AD_SERVIDOR=dc01.empresa.local
# Opcional: por padrão, é DC=empresa,DC=local, derivado do domínio.
AD_BASE_DN=DC=empresa,DC=local
# Opcional se a CA já estiver no repositório de confiança do servidor.
AD_CA_CERTIFICADO=C:/Cnutri/certificados/ca-corporativa.pem
AD_TIMEOUT_SEGUNDOS=5
AD_SESSAO_MINUTOS=30
```

No Windows com `start.ps1`, use `backend/.env`. Em contêiner, injete as variáveis
na configuração privada do serviço backend e monte o arquivo da CA como somente
leitura, usando o caminho de dentro do contêiner em `AD_CA_CERTIFICADO`. O Compose
de produção atual ainda não injeta essas variáveis e o HTTPS permanece pendente;
copiar valores para o `.env` do host, isoladamente, não ativa AD no contêiner.

`AD_SERVIDOR` é o **nome DNS completo do controlador de domínio**, correspondente
ao certificado, sem `ldap://`, sem `ldaps://` e sem porta. O endereço é acessado
somente por **LDAPS na porta 636**, com validação obrigatória de cadeia e nome do
certificado. Não existe opção para ignorar certificado ou usar LDAP sem TLS.
Libere a comunicação do backend para o controlador e confirme a confiança na CA.

O Cnutri usa o próprio usuário no bind e na consulta do `objectGUID`; **não é
necessária uma conta de serviço ou senha administrativa do domínio**. A TI deve
validar que os usuários podem ler `userPrincipalName`, `objectGUID` e
`userAccountControl` no escopo configurado. Falhas de consulta impedem o login.
O Cnutri não altera o diretório e não segue referrals para outros servidores.

## HTTPS e ativação

Antes de mudar `AD_HABILITADO` para `true`, publique o Cnutri por **HTTPS**, com
redirecionamento do endereço HTTP antes da tela de login. A proteção deve cobrir
os dois trechos: navegador → Cnutri e Cnutri → AD. A API rejeita login AD por HTTP.
O Vite de desenvolvimento e o nginx sobrescrevem `X-Forwarded-Proto` com o
protocolo real; um cabeçalho fornecido pelo cliente não libera a autenticação AD.

Na configuração final de HTTPS, mantenha o backend acessível somente ao proxy
confiável. Se houver outro terminador TLS, a TI deve configurar explicitamente
essa cadeia e os cabeçalhos do proxy; não aceite cabeçalhos de origens arbitrárias.
O arquivo nginx atual atende HTTP e não foi convertido para HTTPS nesta entrega.

Depois de configurar o servidor/certificados, reinicie o backend e consulte
Administração → Credenciais. O estado “Integração habilitada” informa a
configuração carregada; não é um teste de conexão com o controlador.
Valide com uma conta de homologação, seus perfis/unidades, senha incorreta,
conta bloqueada/desativada e indisponibilidade do controlador, sem relaxar as
políticas corporativas de autenticação.

## Cadastro e operação

1. Crie ou edite uma credencial e selecione **Active Directory (AD)**.
2. Informe **Usuário no AD** como UPN completo, por exemplo `maria@empresa.local`.
   Use o UPN real, que pode ter um sufixo diferente do domínio DNS.
3. Defina o nome de usuário do Cnutri, nome de exibição, perfil e unidades.
4. Salve. Não informe nem copie a senha da rede para o cadastro.
5. Com a integração ativa e HTTPS, entre com o nome do Cnutri e a senha do AD.

O primeiro login válido fixa o `objectGUID` da conta. Uma conta apagada e recriada
com o mesmo UPN não herda o acesso anterior. Alterar apenas perfil, nome do Cnutri
ou unidades preserva esse vínculo. A TI pode mudar o UPN no cadastro para vincular
outra identidade; essa ação encerra as sessões atuais e exige nova autenticação.
Cada UPN e cada GUID podem pertencer a apenas uma credencial do Cnutri.

Senha inválida, expirada ou bloqueio do AD impedem nova autenticação. Não há
fallback automático para senha local quando o domínio está indisponível. A senha
recebida é utilizada somente durante a requisição e não é persistida. As contas
AD não usam a política local de 8–12 caracteres e não trocam senha pelo Cnutri.

Sessões AD duram no máximo 30 minutos por padrão, limitadas também pela duração
geral configurada. O estado da conta no AD é reavaliado em cada login, **não a
cada requisição da sessão já aberta**. Desativar uma conta no AD bloqueia novos
logins; a sessão já emitida pode durar até expirar. Para corte imediato, desative
a credencial no Cnutri, o que revoga as sessões e encerra os canais privados.
Desativar a integração também invalida o uso dos tokens AD nas APIs protegidas.

Conserve ao menos um **administrador local ativo** para contingência. O sistema
bloqueia a conversão/desativação do último administrador local e a alteração da
origem de autenticação da própria conta administrativa. Converter de AD para
local exige uma nova senha temporária e encerra as sessões anteriores.

## Validação e referências

`backend/tests/test_active_directory.py` testa o cliente LDAP com respostas
simuladas e a autenticação/API em SQLite isolado, sem contactar o domínio real.
O teste de migração PostgreSQL usa um schema exclusivo e transação revertida.
Os testes não substituem a homologação de LDAPS e HTTPS com a infraestrutura da TI.

Referências: [certificados LDAPS — Microsoft](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/configure-ldap-signing-certificates),
[assinatura LDAP — Microsoft](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing),
[TLS e validação de certificados — ldap3](https://ldap3.readthedocs.io/en/latest/ssltls.html).
