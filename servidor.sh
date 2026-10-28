#!/bin/sh
# Comandos de instalação Linux. Não carregue arquivos .env como código de shell.
set -eu
RAIZ=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ACAO=${1:-ajuda}
if [ "$#" -gt 0 ]; then shift; fi

if [ "$ACAO" = configurar ]; then
  if command -v python3 >/dev/null 2>&1; then
    exec python3 "$RAIZ/backend/configurar_servidor.py" "$@"
  fi
  # Alternativa sem Python instalado no host. A imagem pode acompanhar o pacote offline.
  if [ -t 0 ]; then
    exec docker run --rm -it --network none --user "$(id -u):$(id -g)" \
      --mount "type=bind,source=$RAIZ,target=/instalacao" python:3.12-slim \
      python /instalacao/backend/configurar_servidor.py "$@"
  fi
  exec docker run --rm --network none --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$RAIZ,target=/instalacao" python:3.12-slim \
    python /instalacao/backend/configurar_servidor.py "$@"
fi

compose() {
  if [ ! -f "$RAIZ/.env" ] || [ ! -f "$RAIZ/work/servidor.env" ]; then
    echo 'Execute primeiro: ./servidor.sh configurar' >&2
    exit 1
  fi
  if grep -qx 'CNUTRI_HTTPS_ATIVO=true' "$RAIZ/work/servidor.env"; then
    docker compose --project-directory "$RAIZ" --env-file "$RAIZ/.env" \
      --env-file "$RAIZ/work/servidor.env" -f "$RAIZ/docker-compose.prod.yml" \
      -f "$RAIZ/docker-compose.https.yml" "$@"
  else
    docker compose --project-directory "$RAIZ" --env-file "$RAIZ/.env" \
      --env-file "$RAIZ/work/servidor.env" -f "$RAIZ/docker-compose.prod.yml" "$@"
  fi
}

case "$ACAO" in
  validar)
    compose config --quiet
    echo 'Composição válida. DNS, certificado nos dispositivos e equipamentos exigem homologação.'
    ;;
  iniciar)
    compose config --quiet
    compose build
    if grep -qx 'CNUTRI_HTTPS_ATIVO=true' "$RAIZ/work/servidor.env"; then
      compose run --rm --no-deps frontend nginx -t
    fi
    compose up -d --no-build
    ;;
  status) compose ps ;;
  logs) compose logs --tail 80 "$@" ;;
  ajuda|--help|-h)
    echo 'Ceres Care — configuração da instalação Linux'
    echo './servidor.sh configurar [--endereco http://IP:porta] [--alterar]'
    echo './servidor.sh configurar --endereco https://dominio [--certificados /etc/ceres-care/tls] --alterar'
    echo './servidor.sh validar | iniciar | status | logs'
    ;;
  *) echo 'Comando inválido. Use ./servidor.sh ajuda' >&2; exit 1 ;;
esac
