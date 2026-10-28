# Ceres Care — configuração inicial do servidor Linux

O assistente define um endereço público único para esta instalação: protocolo,
IP ou DNS e porta. API e WebSocket acompanham o endereço aberto no navegador;
os atalhos distribuídos pela TI e os novos QR Codes usam o endereço configurado.
Não é necessário editar ou recompilar o React para trocar o IP do servidor.

## Instalação nova

Pré-requisitos: Linux, Docker Engine com Compose e os arquivos do projeto.
O assistente usa Python 3 quando disponível. Caso contrário, usa a imagem oficial
`python:3.12-slim` em contêiner temporário; para instalação offline, essa imagem e
as demais imagens/dependências precisam estar previamente disponíveis.

Na pasta da instalação, execute:

```sh
sh ./servidor.sh configurar
```

Informe o endereço que os computadores, celulares e tablets usarão para acessar
o servidor. O assistente aceita HTTP inicialmente e HTTPS após a TI disponibilizar
DNS e certificados. Não use localhost, 127.0.0.1 ou 0.0.0.0 como endereço distribuído.

Também é possível informar o endereço no comando. **Substitua o IP de exemplo
abaixo pelo endereço real do destino**; 192.0.2.10 é apenas documentação:

```sh
sh ./servidor.sh configurar --endereco http://192.0.2.10:8080
sh ./servidor.sh validar
sh ./servidor.sh iniciar
```

O assistente apenas prepara os arquivos. `validar` confere o modelo Compose;
`iniciar` constrói as imagens na instalação pelo código-fonte e inicia os serviços.
No pacote executável `.run`, utiliza as imagens já incluídas, sem compilar ou baixar.
DNS, alcance da rede, impressão
e confiança do certificado nos dispositivos exigem a [homologação](HOMOLOGACAO-LINUX.md).

Arquivos privados gerados:

- `work/servidor.env`: endereço, portas, modo HTTP/HTTPS e pasta dos certificados.
- `.env`: segredos exclusivos de uma instalação nova, somente se ainda não existir.
- `work/credencial-inicial.txt`: acesso inicial de `admin`, apenas na instalação nova.
  A senha tem troca obrigatória no primeiro acesso e não aparece na saída do comando.

Os arquivos têm acesso restrito ao usuário da instalação no Linux e ficam fora do
Git. O assistente não acessa banco, DNS, AD ou impressoras. Credenciais e segredos
existentes são mantidos; o arquivo inicial não redefine usuários de bases restauradas.

## Consultar e distribuir os acessos

```sh
sh ./servidor.sh status
sh ./servidor.sh logs backend
```

Entre em `/admin` e abra **Servidor da aplicação** para consultar o endereço e os
links de login, administração e gestão. Na aba **Unidades**, os atalhos `.url` usam
o servidor definido na instalação, mesmo se a TI acessou o painel por localhost.
Formulários e cozinhas continuam usando o nome cadastrado de cada unidade.
Sem a nova configuração, instalações anteriores mantêm seus endereços e fluxo.

## Mudar servidor, domínio ou porta

Prepare a mudança explicitamente e aplique na janela de manutenção:

```sh
sh ./servidor.sh configurar --endereco http://192.0.2.20:8080 --alterar
sh ./servidor.sh validar
sh ./servidor.sh iniciar
```

O arquivo anterior é preservado em `work/servidor.env.anterior`. A alteração não
migra dados para outra máquina: uma mudança física de servidor exige copiar os
arquivos privados, restaurar o banco e conferir o destino antes da abertura ao uso.
Mantenha o nome do projeto Compose/volume da instalação e os segredos correspondentes.

## Ativar HTTPS posteriormente

Disponibilize `servidor.pem` (certificado e intermediários) e `chave.pem` em uma
pasta privada no Linux, com DNS e cadeia de confiança configurados pela TI:

```sh
sh ./servidor.sh configurar --endereco https://cnutri.preventsenior.com.br \
  --certificados /etc/ceres-care/tls --alterar
sh ./servidor.sh validar
sh ./servidor.sh iniciar
```

O exemplo de domínio também deve ser ajustado ao DNS aprovado para o destino.
Pode-se informar uma porta HTTPS diferente, como `:8443`. A porta HTTP anterior é
mantida para o redirecionamento. `iniciar` valida o Nginx com os arquivos TLS em
contêiner temporário antes de ativar os serviços HTTPS.

O endereço central também passa a reger os novos QR Codes e as origens permitidas
da API. `URL_RECEBIMENTO_PUBLICA` continua compatível com versões anteriores; quando
`URL_PUBLICA` está definida, ela é a referência principal. A consulta pública
`/api/configuracao/instalacao` expõe somente esse endereço, sem segredos ou dados clínicos.

Ative na janela combinada, com backup e sem trabalhos de impressão em processamento.
Entre novamente no endereço HTTPS. QR Codes já impressos conservam seu endereço:
mantenha o domínio estável ou providencie redirecionamento do endereço antigo.
Detalhes dos certificados: [HTTPS.md](HTTPS.md).

## Verificação desta implementação

Os testes usam pastas temporárias, segredos fictícios, Linux em contêiner isolado e
certificados descartáveis. Conferem manutenção das credenciais, portas, atalhos,
redirecionamento HTTPS e compatibilidade do QR. Isso não equivale à homologação
do futuro servidor, da rede hospitalar ou das impressoras reais.
