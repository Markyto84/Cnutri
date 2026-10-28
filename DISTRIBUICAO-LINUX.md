# Ceres Care — executável de instalação Linux

O arquivo `ceres-care-VERSAO-linux-amd64.run` é um instalador executável com carga
compactada. Inclui imagens Docker da API, interface compilada, PostgreSQL vazio
e Python usado pelo assistente. A plataforma desta distribuição é **linux/amd64**,
para servidores Linux Intel/AMD 64 bits.

O destino precisa ter Docker Engine e plugin Compose funcionando. Os componentes
da aplicação estão no pacote; não há compilação, instalação de bibliotecas Python
ou download de dependências no servidor de destino. O Docker pode precisar de
acesso à internet para sua instalação e futuras atualizações, fora deste pacote.

## Usar o arquivo recebido

Copie `.run` e `.run.sha256` para o servidor e confira a soma indicada. Para abrir
o assistente de instalação nova:

```sh
sudo sh ./ceres-care-VERSAO-linux-amd64.run
```

Ele solicita o endereço da aplicação, carrega as imagens locais e prepara os
serviços em `/opt/ceres-care`. A pasta de destino precisa estar ausente. O instalador
recusa uma instalação ou volume anterior do projeto `ceres-care`, preservando-os.
Migração do banco Windows e atualização de uma instalação existente exigem um
procedimento próprio; esse instalador não transfere nem substitui dados existentes.

Opções: `--ajuda`, `--verificar`, `--extrair /pasta/nova`, `--destino /pasta/nova`,
`--endereco http://IP:porta` e `--certificados /etc/ceres-care/tls`.

Após instalar, use o arquivo privado `work/credencial-inicial.txt` para o primeiro
login; a senha precisa ser trocada. HTTPS pode ser configurado posteriormente,
conforme [Instalação do servidor](INSTALACAO-SERVIDOR.md). Conclua a
[homologação](HOMOLOGACAO-LINUX.md) no servidor e nos equipamentos da unidade.

## Gerar uma distribuição

Na estação de preparação, com Python 3, Git e Docker Linux/amd64:

```sh
python backend/gerar_instalador.py --versao 0.1.0 --saida dist
```

O gerador constrói as imagens, exporta somente imagens (nunca volumes ou bancos)
e copia uma lista explícita de arquivos. Segredos, certificados reais, logs, dados
de pacientes, `.env`, backups e dependências da estação não entram no pacote.
Os contextos Docker têm `.dockerignore` para impedir cópia de ambientes privados
e dependências Windows durante o build Linux.

O arquivo `release.json` registra revisão Git, versão, IDs das imagens e hashes
dos arquivos. O `.sha256` acompanha o executável; conferir a soma detecta danos
na transferência, sem constituir assinatura digital do editor.

Os testes de geração/extração usam carga fictícia, sem serviços reais. O teste de
instalação da versão final deve usar banco novo e rede/portas isoladas. Essa prova
do pacote não substitui o teste de impressoras, DNS, certificados e restauração
no servidor definitivo.
