# HTTPS do Cnutri

O projeto tem configuração de HTTPS para a instalação Windows atual e para o
servidor Linux em Docker. **Preparar os arquivos não ativa HTTPS.** É necessário
informar o endereço da aplicação e o certificado de servidor com sua chave privada.
O domínio do AD, sozinho, não define o endereço HTTPS do Cnutri.

## Endereço solicitado: cnutri.preventsenior.com.br

O destino solicitado para a intranet é `https://cnutri.preventsenior.com.br`.
Na verificação de 27/10/2026, a instalação em uso responde em
`http://10.1.140.15:5173`. Os dois DNS consultados da rede retornaram nome inexistente,
e nenhum certificado correspondente foi localizado nos arquivos da instalação
ou nos repositórios pessoais de certificados do Windows consultados.

Para concluir:

1. A TI deve cadastrar o registro **A** `cnutri.preventsenior.com.br` no DNS interno
   apontando para **10.1.140.15**, com o IP fixo ou reservado para esta instalação.
2. Disponibilizar certificado/cadeia e chave válidos para esse nome, ou um PFX.
   Informe somente os caminhos dos arquivos; senhas e chaves ficam fora do chat/Git.
3. Executar o configurador abaixo com `-Dominio 'cnutri.preventsenior.com.br'`
   e os arquivos reais. O configurador valida DNS, certificado e conexão antes da troca.
4. Após confirmar o novo HTTPS, atualizar `URL_RECEBIMENTO_PUBLICA` no ambiente privado
   do backend para `https://cnutri.preventsenior.com.br` e reiniciar somente a API,
   conferindo antes que não haja trabalhos de impressão em processamento.
5. Conferir os formulários de cada unidade, login, cozinha, entregas e atualizações
   em tempo real pelo novo domínio. Os caminhos das páginas permanecem os mesmos.

O servidor atual já aceita explicitamente esse nome no Vite, conforme
[allowedHosts](https://vite.dev/config/server-options.html#server-allowedhosts).
Após o cadastro DNS, o acesso HTTP atual também poderá usar o nome na porta 5173;
o HTTPS sem porta depende da ativação acima. A configuração dos novos QR Codes
permanece no endereço atual até a validação do novo acesso. O proxy HTTPS redireciona
as portas HTTP 80 e 5173 para o domínio escolhido.

O cadastro é feito no DNS que atende os dispositivos da intranet. Consulte a
[documentação da Microsoft sobre registros DNS](https://learn.microsoft.com/en-us/windows-server/networking/dns/manage-resource-records).

## Dados necessários da TI

- Nome DNS reservado ao Cnutri, por exemplo `cnutri.empresa.local`, resolvendo para
  o IP do servidor correto.
- Certificado válido para esse nome na extensão **SAN**, com uso de autenticação
  de servidor. Pode ser PEM (certificado/cadeia e chave) ou PFX com a chave privada.
- Cadeia da CA confiável no servidor, nas estações Chrome e nos celulares usados.
- Liberação de TCP 443; TCP 80 e, na instalação Windows, 5173 para redirecionar os
  endereços antigos. A TI define o escopo de rede permitido no firewall.

Não envie chaves ou senhas pelo chat. Arquivos reais ficam fora do Git. O
configurador valida nome/SAN, validade, correspondência de chave e uso do
certificado antes de preparar a ativação. Não instala uma CA, não altera DNS nem
ignora avisos de certificado.

## Windows — instalação atual

O HTTPS usa Caddy com o frontend compilado, sem publicar o servidor Vite. A API
continua em `127.0.0.1:8000`, com o mesmo banco e os mesmos usuários. Os comandos
`start.ps1` e `stop.ps1` passam a administrar o frontend HTTPS quando a
configuração privada ativa existe.

Na pasta do projeto, com os arquivos fornecidos pela TI:

```powershell
# Somente preparar e validar; mantém o acesso atual.
.\configurar-https.ps1 -Dominio 'cnutri.empresa.local' `
  -Certificado 'C:\TI\cnutri-cadeia.pem' -Chave 'C:\TI\cnutri-chave.pem'

# Preparar e ativar após DNS e certificados estarem corretos.
.\configurar-https.ps1 -Dominio 'cnutri.empresa.local' `
  -Certificado 'C:\TI\cnutri-cadeia.pem' -Chave 'C:\TI\cnutri-chave.pem' -Aplicar

# Alternativa PFX: a senha é solicitada no terminal local, com entrada oculta.
.\configurar-https.ps1 -Dominio 'cnutri.empresa.local' -Pfx 'C:\TI\cnutri.pfx' -Aplicar
```

O arquivo PEM da chave deve estar legível sem senha pelo serviço. Se a TI fornece
uma chave protegida, use um PFX e informe a senha somente no terminal local. O
configurador exporta a chave para uma geração privada em `work/https/generations/`,
com ACL restrita ao usuário atual e ao SYSTEM. Preserve a proteção desses arquivos
ao transferir para o novo servidor ou escolher a conta que executará o serviço.

O Caddy 2.11.7 é obtido da distribuição oficial. O instalador confere o SHA-256
fixado em `infra/caddy-release.json` antes de extrair o executável em `work/runtime/`.
Certificados, chaves e binários não são versionados.

Ao aplicar, o configurador:

1. Gera o frontend e valida a configuração do servidor.
2. Confere se o DNS aponta para esta estação e se as portas pertencem ao projeto.
3. Inicia uma sonda em `127.0.0.1:8443` e valida a conexão TLS com a confiança real
   do Windows/Python, incluindo nome do servidor e resposta da API.
4. Troca somente o frontend. A API e o PostgreSQL permanecem em uso.
5. Confere o acesso HTTPS final. Se a troca falhar, restaura a configuração anterior.

Após a ativação, os endereços ficam assim:

| Uso | Endereço |
| --- | --- |
| Formulário | `https://cnutri.empresa.local/unidade-havai` |
| Login | `https://cnutri.empresa.local/login` |
| Gestão | `https://cnutri.empresa.local/gestao` |
| Administração | `https://cnutri.empresa.local/admin` |
| Cozinha | `https://cnutri.empresa.local/cozinha/1` |
| Entregas | `https://cnutri.empresa.local/entregas/1` |

HTTP nas portas 80 e 5173 redireciona para o nome configurado, preservando caminho
e parâmetros. O destino não usa o cabeçalho Host enviado pelo cliente. As
atualizações em tempo real passam por WSS. A aplicação usa o certificado fornecido
pela TI; não solicita certificados públicos ou gera uma CA automaticamente.

Atualize a página e entre novamente no novo endereço. Tokens guardados no endereço
HTTP anterior não são copiados entre origens. A mudança não redefine senhas nem
altera cadastros. O AD continua desativado até sua configuração e homologação próprias.

Para renovar o certificado, repita o configurador com os novos arquivos antes do
vencimento. A geração anterior permanece disponível para reversão. Logs e estado
ficam em `work/logs/`, `work/https/` e `work/servicos.json`. O HTTPS usa os mesmos
scripts de inicialização existentes; esta etapa não instala serviço do Windows ou
inicialização automática após reiniciar o computador.

## Linux/Docker — servidor de destino

Na instalação de produção já preparada, disponibilize a pasta privada com
`servidor.pem` (certificado + intermediários) e `chave.pem`. Defina no ambiente
privado do Compose:

```dotenv
CNUTRI_HOSTNAME=cnutri.empresa.local
CNUTRI_TLS_DIR=/etc/cnutri/tls
```

Com o mesmo nome de projeto Compose, volume e ambiente da instalação existente:

```sh
docker compose -f docker-compose.prod.yml -f docker-compose.https.yml config --quiet
docker compose -f docker-compose.prod.yml -f docker-compose.https.yml up -d --build frontend
```

O complemento usa nginx na porta 443 e redireciona a porta 80. Os arquivos TLS são
montados somente para leitura, fora da pasta pública da aplicação. O proxy
sobrescreve os cabeçalhos de protocolo/IP e mantém suporte a WebSocket. A API e o
banco não publicam portas externas nessa composição.

Não execute essa composição para substituir diretamente o ambiente Windows:
o volume de produção é separado do PostgreSQL de desenvolvimento. A transferência
dos dados para outro servidor exige backup/restauração e conferência próprios.

## Verificação realizada

- Testes geram certificados e CA **descartáveis**, sem instalar confiança no sistema.
- Conferência de SAN, chave, validade, uso TLS e importação de PFX protegido.
- Gateway real em portas locais de teste: HTTPS, redirecionamento 308 das duas
  portas HTTP, caminho/parâmetros, SPA, API, WSS e rejeição de cabeçalhos forjados.
- Rejeição de CA não confiável e de nome TLS incorreto.
- O teste em Docker usa certificado fictício e `nginx -t`, sem publicar portas
  ou acessar o PostgreSQL do hospital.

As verificações não equivalem à validação do certificado real da TI e do acesso
por outras máquinas; essas dependem dos arquivos, DNS e confiança corporativos.

Referências: [TLS no Caddy](https://caddyserver.com/docs/caddyfile/directives/tls),
[proxy e WebSocket no Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[HTTPS no nginx](https://nginx.org/en/docs/http/configuring_https_servers.html).
