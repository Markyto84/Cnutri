#!/bin/sh
# Cabeçalho do instalador Linux; a carga compactada é anexada pelo gerador.
set -eu
VERSAO='__VERSAO__'
SHA_ESPERADO='__PAYLOAD_SHA256__'
DESTINO=/opt/ceres-care
MODO=instalar
ENDERECO=''
CERTIFICADOS=''

falhar() { printf '%s\n' "$1" >&2; exit 1; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --destino|--extrair|--endereco|--certificados)
      [ "$#" -ge 2 ] || falhar "Falta o valor de $1."
      case "$1" in
        --destino) DESTINO=$2 ;;
        --extrair) MODO=extrair; DESTINO=$2 ;;
        --endereco) ENDERECO=$2 ;;
        --certificados) CERTIFICADOS=$2 ;;
      esac
      shift 2
      ;;
    --verificar) MODO=verificar; shift ;;
    --ajuda|--help|-h)
      printf '%s\n' "Ceres Care $VERSAO — instalador Linux x86_64" \
        'Uso: sudo sh arquivo.run [--destino /opt/ceres-care] [--endereco http://IP:porta]' \
        'HTTPS: acrescentar --certificados /etc/ceres-care/tls' \
        'Somente conferir: sh arquivo.run --verificar' \
        'Somente extrair: sh arquivo.run --extrair /pasta/nova' \
        'Requer Docker Engine e plugin Docker Compose já instalados no servidor.'
      exit 0
      ;;
    *) falhar "Opção desconhecida: $1. Consulte --ajuda." ;;
  esac
done

for programa in awk tail sha256sum tar gzip; do
  command -v "$programa" >/dev/null 2>&1 || falhar "Componente Linux ausente: $programa."
done
LINHA=$(awk '/^__CERES_CARE_ARQUIVO__$/ { print NR + 1; exit }' "$0")
[ -n "$LINHA" ] || falhar 'Pacote sem conteúdo de instalação.'
SHA_ATUAL=$(tail -n "+$LINHA" "$0" | sha256sum | awk '{print $1}')
[ "$SHA_ATUAL" = "$SHA_ESPERADO" ] || falhar 'Falha de integridade: copie novamente o instalador original.'
printf '%s\n' "Ceres Care $VERSAO: integridade do pacote conferida."
[ "$MODO" != verificar ] || exit 0

[ "$(uname -s)" = Linux ] || falhar 'Este instalador requer um servidor Linux.'
case "$(uname -m)" in x86_64|amd64) ;; *) falhar 'Este pacote foi preparado para Linux x86_64 (Intel/AMD 64 bits).' ;; esac
case "$DESTINO" in /*) ;; *) falhar 'Informe uma pasta de destino absoluta.' ;; esac
if [ -e "$DESTINO" ] || [ -L "$DESTINO" ]; then
  falhar 'O destino já existe. A instalação nova não substitui arquivos ou bancos de uma instalação anterior.'
fi
[ -d "$(dirname -- "$DESTINO")" ] || falhar 'A pasta pai do destino precisa existir.'

if [ "$MODO" = instalar ]; then
  command -v docker >/dev/null 2>&1 || falhar 'Instale Docker Engine e o plugin Docker Compose antes de executar o instalador.'
  docker info >/dev/null 2>&1 || falhar 'O Docker não está respondendo ou o usuário não tem acesso. Confira o serviço e as permissões.'
  docker compose version >/dev/null 2>&1 || falhar 'O plugin Docker Compose não está disponível.'
  EXISTENTES=$(docker ps -aq --filter label=com.docker.compose.project=ceres-care)
  VOLUMES=$(docker volume ls -q --filter label=com.docker.compose.project=ceres-care)
  [ -z "$EXISTENTES$VOLUMES" ] || falhar 'Já existe uma instalação ou banco do projeto ceres-care neste Docker. Use o procedimento de atualização/migração da TI.'
fi

umask 077
mkdir -m 700 -- "$DESTINO"
tail -n "+$LINHA" "$0" | gzip -dc | tar -xf - -C "$DESTINO"
printf '%s\n' "Arquivos extraídos em: $DESTINO"
if [ "$MODO" = extrair ]; then
  printf '%s\n' 'Consulte LEIA-ME.md para carregar as imagens e concluir a instalação.'
  exit 0
fi

printf '%s\n' 'Carregando as imagens da aplicação, do banco e do assistente...'
docker load --input "$DESTINO/imagens.tar"
set -- configurar
[ -z "$ENDERECO" ] || set -- "$@" --endereco "$ENDERECO"
[ -z "$CERTIFICADOS" ] || set -- "$@" --certificados "$CERTIFICADOS"
sh "$DESTINO/servidor.sh" "$@"
sh "$DESTINO/servidor.sh" validar
sh "$DESTINO/servidor.sh" iniciar
printf '%s\n' "Instalação concluída. Consulte $DESTINO/work/credencial-inicial.txt no servidor para o primeiro acesso."
printf '%s\n' 'A homologação da rede, dos dispositivos e das impressoras deve ser concluída pela TI.'
exit 0
__CERES_CARE_ARQUIVO__
