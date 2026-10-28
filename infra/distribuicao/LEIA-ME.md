# Ceres Care — pacote executável Linux x86_64

Este pacote contém as imagens compiladas da aplicação, PostgreSQL e Python para
o assistente. A instalação da aplicação pode funcionar sem internet após o Docker
Engine e seu plugin Compose já estarem instalados e funcionando no servidor.

## Instalação nova

Copie o arquivo `.run` e seu `.sha256` para o servidor Linux Intel/AMD 64 bits.
Na pasta dos arquivos, confira a cópia:

```sh
sha256sum -c ceres-care-__VERSAO__-linux-amd64.run.sha256
sh ceres-care-__VERSAO__-linux-amd64.run --verificar
sudo sh ceres-care-__VERSAO__-linux-amd64.run
```

O instalador solicita o endereço do servidor. Também aceita `--endereco` e
`--destino`; consulte `--ajuda`. O destino padrão é `/opt/ceres-care` e precisa
estar ausente antes da instalação. Arquivos existentes não são substituídos.

A senha inicial fica somente em `work/credencial-inicial.txt`, no servidor, com
acesso restrito. O primeiro login de `admin` exige sua troca. O pacote distribuído
não contém contas, senhas, dados de pacientes, backups nem certificados reais.

## Extração e retomada manual

```sh
sh ceres-care-__VERSAO__-linux-amd64.run --extrair /opt/ceres-care
cd /opt/ceres-care
sudo docker load --input imagens.tar
sudo sh ./servidor.sh configurar
sudo sh ./servidor.sh validar
sudo sh ./servidor.sh iniciar
```

A distribuição usa o projeto Compose `ceres-care`. Uma instalação existente desse
projeto exige atualização/migração própria; a execução normal do instalador recusa
esse caso. Não reutilize um volume existente com os novos segredos gerados para
uma instalação vazia. O banco da estação Windows não é transferido pelo `.run`.

## Depois da instalação

- `sh ./servidor.sh status`: estado dos serviços.
- `sh ./servidor.sh logs backend`: últimas mensagens da API.
- `sh ./servidor.sh configurar --endereco https://DOMINIO --certificados /etc/ceres-care/tls --alterar`:
  preparar HTTPS posteriormente; aplicar com `validar` e `iniciar` na janela combinada.
- Habilitar o Docker na inicialização do Linux e definir backup externo e retenção.
  Os contêineres usam a política `unless-stopped`.

Leia `INSTALACAO-SERVIDOR.md`, `HTTPS.md` e `HOMOLOGACAO-LINUX.md` para as próximas
etapas. As imagens já estão compiladas: os comandos de início desta distribuição
usam somente as imagens locais, sem baixar pacotes ou compilar no destino.

`release.json` registra versão, revisão, imagens e hashes dos arquivos do pacote.
As somas SHA-256 verificam a integridade da cópia; não são uma assinatura digital
do editor. Guarde o instalador original em um local controlado pela TI.
