"""Gera um .run Linux com imagens Docker locais e arquivos explicitamente permitidos."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
ARQUIVOS = (
    "servidor.sh", "backend/configurar_servidor.py", "backend/app/core/endereco_publico.py",
    "docker-compose.https.yml", "infra/nginx-https.conf.template", "infra/https.env.example",
    "INSTALACAO-SERVIDOR.md", "HTTPS.md", "HOMOLOGACAO-LINUX.md",
    "MONITORAMENTO-E-RECUPERACAO.md", "ACTIVE-DIRECTORY.md",
)


def sha256(arquivo):
    resultado = hashlib.sha256()
    with Path(arquivo).open("rb") as entrada:
        for bloco in iter(lambda: entrada.read(8 * 1024 * 1024), b""):
            resultado.update(bloco)
    return resultado.hexdigest()


def versao_valida(valor):
    if len(valor) > 60 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?", valor):
        raise ValueError("Use uma versão como 0.1.0 ou 0.1.0-rc1.")
    return valor


def preparar_conteudo(raiz, destino, versao):
    versao_valida(versao)
    for relativo in ARQUIVOS:
        origem = raiz / relativo
        if origem.is_symlink() or not origem.is_file():
            raise ValueError(f"Arquivo de distribuição ausente ou simbólico: {relativo}")
        alvo = destino / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        # Os scripts precisam de LF mesmo quando a distribuição é gerada no Windows.
        alvo.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        alvo.chmod(0o755 if alvo.suffix == ".sh" else 0o644)
    compose = (raiz / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for servico in ("backend", "frontend"):
        anterior = f"    build: ./{servico}"
        if compose.count(anterior) != 1:
            raise ValueError("A estrutura Compose mudou; revise o gerador antes de distribuir.")
        compose = compose.replace(anterior, f"    image: ceres-care/{servico}:{versao}\n    pull_policy: never")
    compose = compose.replace("    image: postgres:16-alpine", "    image: postgres:16-alpine\n    pull_policy: never")
    compose = re.sub(r"^    container_name: .+\n", "", compose, flags=re.MULTILINE)
    if re.search(r"^\s*build:", compose, re.MULTILINE):
        raise ValueError("A distribuição não pode depender de compilação no destino.")
    (destino / "docker-compose.prod.yml").write_text("name: ceres-care\n\n" + compose, encoding="utf-8", newline="\n")
    leia = (raiz / "infra/distribuicao/LEIA-ME.md").read_text(encoding="utf-8").replace("__VERSAO__", versao)
    (destino / "LEIA-ME.md").write_text(leia, encoding="utf-8", newline="\n")


def gerar_run(conteudo, saida, versao, *, revisao, imagens):
    versao_valida(versao)
    manifesto = {"produto": "Ceres Care", "versao": versao, "plataforma": "linux/amd64",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(), "revisao_git": revisao,
        "imagens": imagens, "arquivos": {}}
    for arquivo in sorted(conteudo.rglob("*")):
        if arquivo.is_symlink():
            raise ValueError("Links simbólicos não são permitidos no pacote.")
        if arquivo.is_file():
            relativo = arquivo.relative_to(conteudo).as_posix()
            if any(p in (".env", ".git", "backups", "work", ".venv", "node_modules") for p in Path(relativo).parts) or arquivo.suffix.lower() in (".pem", ".key", ".pfx", ".p12", ".crt", ".cer"):
                raise ValueError("Arquivo privado ou de desenvolvimento encontrado no conteúdo.")
            manifesto["arquivos"][relativo] = {"sha256": sha256(arquivo), "bytes": arquivo.stat().st_size}
    (conteudo / "release.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    carga = conteudo.parent / "conteudo.tar.gz"
    with tarfile.open(carga, "w:gz", compresslevel=6) as tar:
        for arquivo in sorted(conteudo.rglob("*")):
            if arquivo.is_file():
                info = tar.gettarinfo(str(arquivo), arcname=arquivo.relative_to(conteudo).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mode = 0o755 if arquivo.suffix == ".sh" else 0o644
                with arquivo.open("rb") as entrada:
                    tar.addfile(info, entrada)
    cabecalho = (ROOT / "infra/distribuicao/instalador.sh").read_text(encoding="utf-8")
    cabecalho = cabecalho.replace("__VERSAO__", versao).replace("__PAYLOAD_SHA256__", sha256(carga))
    saida.parent.mkdir(parents=True, exist_ok=True)
    if saida.exists():
        raise ValueError("O arquivo de saída já existe; escolha outro destino ou versão.")
    with saida.open("xb") as arquivo, carga.open("rb") as entrada:
        arquivo.write((cabecalho.rstrip("\n") + "\n").encode("utf-8"))
        shutil.copyfileobj(entrada, arquivo, length=8 * 1024 * 1024)
    saida.chmod(0o755)
    digest = sha256(saida)
    saida.with_suffix(saida.suffix + ".sha256").write_text(f"{digest}  {saida.name}\n", encoding="ascii")
    return {"arquivo": str(saida), "bytes": saida.stat().st_size, "sha256": digest}


def principal():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versao", default="0.1.0")
    parser.add_argument("--saida", type=Path, default=ROOT / "dist")
    parser.add_argument("--sem-compilar", action="store_true", help="Usar imagens locais já compiladas desta versão")
    args = parser.parse_args()
    versao = versao_valida(args.versao)
    saida = args.saida.resolve() / f"ceres-care-{versao}-linux-amd64.run"
    if saida.exists():
        raise SystemExit("Saída já existente; escolha outra pasta ou versão.")
    for servico in ("backend", "frontend"):
        if not args.sem_compilar:
            print(f"Compilando {servico} para Linux x86_64...", flush=True)
            subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", f"ceres-care/{servico}:{versao}", str(ROOT / servico)], check=True)
    tags = [f"ceres-care/backend:{versao}", f"ceres-care/frontend:{versao}", "postgres:16-alpine", "python:3.12-slim"]
    imagens = {}
    for tag in tags:
        dados = json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]
        if dados["Os"] != "linux" or dados["Architecture"] != "amd64":
            raise SystemExit(f"Imagem incompatível com o destino linux/amd64: {tag}")
        imagens[tag] = {"id": dados["Id"], "plataforma": "linux/amd64"}
    revisao = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    pasta_work = ROOT / "work"
    pasta_work.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="distribuicao-", dir=pasta_work) as temporario:
        conteudo = Path(temporario) / "conteudo"
        conteudo.mkdir()
        preparar_conteudo(ROOT, conteudo, versao)
        dependencias = subprocess.check_output(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python", tags[0], "-m", "pip", "freeze"], text=True)
        (conteudo / "dependencias-python.txt").write_text(dependencias, encoding="utf-8")
        print("Reunindo imagens Docker locais; nenhum banco ou volume será exportado...", flush=True)
        subprocess.run(["docker", "image", "save", "--output", str(conteudo / "imagens.tar"), *tags], check=True)
        print("Compactando o executável de instalação...", flush=True)
        resultado = gerar_run(conteudo, saida, versao, revisao=revisao, imagens=imagens)
    print(json.dumps(resultado, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    principal()
