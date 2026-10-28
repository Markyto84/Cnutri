"""Laboratório Docker descartável, vinculado somente ao localhost do executor."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import subprocess
import ssl
import time
from uuid import uuid4

import httpx

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import ipaddress

ROOT = Path(__file__).resolve().parents[1]


class Laboratorio:
    def __init__(self):
        self.projeto = "ceres-carga-" + uuid4().hex[:12]
        self.pasta = ROOT / "work" / self.projeto
        self.pasta.mkdir(mode=0o700, parents=True)
        self.modelo = self.pasta / "compose.json"
        self.cacert = self.pasta / "tls/ca.pem"
        self.ids = {}
        self.criar_modelo()

    def comando(self, *args, capturar=True, entrada=None, verificar=True):
        r = subprocess.run(["docker", "compose", "--project-name", self.projeto, "-f", str(self.modelo), *args],
            input=entrada, text=True, encoding="utf-8", capture_output=capturar, check=verificar)
        return r.stdout.strip() if capturar else ""

    def criar_modelo(self):
        tls = self.pasta / "tls"
        tls.mkdir()
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        agora = datetime.now(timezone.utc)
        nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA FICTICIA TESTE DE CARGA")])
        ca = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(agora-timedelta(hours=1)).not_valid_after(agora+timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True).sign(ca_key, hashes.SHA256()))
        servidor = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "carga.invalid")]))
            .issuer_name(nome).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(agora-timedelta(hours=1)).not_valid_after(agora+timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("carga.invalid"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .sign(ca_key, hashes.SHA256()))
        self.cacert.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        (tls / "servidor.pem").write_bytes(servidor.public_bytes(serialization.Encoding.PEM)+ca.public_bytes(serialization.Encoding.PEM))
        (tls / "chave.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        binds = [{"type": "bind", "source": str(ROOT / "performance"), "target": "/lab", "read_only": True},
            {"type": "bind", "source": str(ROOT / "configuracoes/formularios-unidade-havai.json"), "target": "/config/formularios.json", "read_only": True},
            {"type": "bind", "source": str(self.pasta), "target": "/resultados"}]
        senha = secrets.token_hex(24)
        self.dados = {"name": self.projeto, "services": {
            "db": {"image": "postgres:16-alpine", "cpus": 2.0, "mem_limit": "4g", "environment": {"POSTGRES_USER": "dietas", "POSTGRES_DB": "dietas", "POSTGRES_PASSWORD": senha},
                "volumes": ["pgdata:/var/lib/postgresql/data"], "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U dietas"], "interval": "2s", "timeout": "2s", "retries": 20}},
            "backend": {"image": "ceres-care/backend:0.1.0", "cpus": 1.5, "mem_limit": "2g", "environment": {
                "APP_ENV": "production", "JWT_SECRET": secrets.token_urlsafe(48), "ADMIN_INICIAL_SENHA": "CargaTeste@1",
                "DATABASE_URL": f"postgresql+asyncpg://dietas:{senha}@db:5432/dietas", "URL_PUBLICA": "https://carga.invalid", "URL_RECEBIMENTO_PUBLICA": "https://carga.invalid",
                "FORWARDED_ALLOW_IPS": "*", "SIMULACAO_PICO": "1"}, "volumes": binds,
                "depends_on": {"db": {"condition": "service_healthy"}}},
            "frontend": {"image": "ceres-care/frontend:0.1.0", "cpus": 0.5, "mem_limit": "256m", "ports": ["127.0.0.1::443"],
                "environment": {"CNUTRI_HOSTNAME": "carga.invalid", "CNUTRI_URL_PUBLICA": "https://carga.invalid"},
                "volumes": [{"type": "bind", "source": str(ROOT / "infra/nginx-https.conf.template"), "target": "/etc/nginx/templates/default.conf.template", "read_only": True},
                    {"type": "bind", "source": str(tls), "target": "/etc/nginx/cnutri-tls", "read_only": True}], "depends_on": ["backend"]},
            "impressora": {"image": "python:3.12-slim", "cpus": 0.25, "mem_limit": "64m", "command": ["python", "/lab/servicos_lab.py"],
                "volumes": [binds[0]], "ports": ["127.0.0.1::9000"]},
        }, "volumes": {"pgdata": {}}}
        self.salvar()

    def salvar(self):
        self.modelo.write_text(json.dumps(self.dados), encoding="utf-8")

    @classmethod
    def carregar(cls, pasta, *, conectar=True):
        lab = cls.__new__(cls)
        lab.pasta = Path(pasta).resolve()
        assert lab.pasta.parent == (ROOT / "work").resolve() and lab.pasta.name.startswith("ceres-carga-")
        lab.modelo = lab.pasta / "compose.json"
        lab.dados = json.loads(lab.modelo.read_text(encoding="utf-8"))
        lab.projeto = lab.dados["name"]
        assert lab.projeto == lab.pasta.name
        lab.cacert = lab.pasta / "tls/ca.pem"
        lab.ids = {}
        if conectar:
            lab.unidades = json.loads((lab.pasta / "unidades-privado.json").read_text(encoding="utf-8"))
            lab.ids = {s: lab.comando("ps", "-q", s) for s in ("backend", "db", "frontend")}
            lab.url = f"https://127.0.0.1:{lab.porta('frontend',443)}"
        return lab

    def inspecionar(self, servico):
        identificador = self.comando("ps", "-q", servico)
        assert identificador
        return json.loads(subprocess.check_output(["docker", "inspect", identificador], text=True))[0]

    def porta(self, servico, porta):
        dados = self.inspecionar(servico)
        return int(dados["NetworkSettings"]["Ports"][f"{porta}/tcp"][0]["HostPort"])

    def iniciar(self):
        assert self.projeto.startswith("ceres-carga-")
        self.comando("up", "-d", "--no-build", "--pull", "never", capturar=False)
        self.url = f"https://127.0.0.1:{self.porta('frontend',443)}"
        contexto = ssl.create_default_context(cafile=str(self.cacert))
        with httpx.Client(verify=contexto, timeout=3) as cliente:
            for tentativa in range(45):
                try:
                    if cliente.get(self.url + "/api/health/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if tentativa == 44:
                    raise RuntimeError("O laboratório não ficou pronto")
                time.sleep(1)
        impressora = self.inspecionar("impressora")
        ip = next(iter(impressora["NetworkSettings"]["Networks"].values()))["IPAddress"]
        self.comando("exec", "-T", "--env", f"IMPRESSORA_SIMULADA_IP={ip}", "backend", "python", "/lab/preparar.py", capturar=False)
        self.unidades = json.loads((self.pasta / "unidades-privado.json").read_text(encoding="utf-8"))
        self.url = f"https://127.0.0.1:{self.porta('frontend',443)}"
        for nome in ("backend", "db", "frontend"):
            self.ids[nome] = self.comando("ps", "-q", nome)

    def sql(self, sql):
        return self.comando("exec", "-T", "db", "psql", "-X", "-At", "-U", "dietas", "-d", "dietas", "-v", "ON_ERROR_STOP=1", entrada=sql)

    def fila(self, minimo):
        return json.loads(self.sql(f"""SELECT json_build_object('pendentes',count(*) FILTER (WHERE estado IN ('PENDENTE','PROCESSANDO')),
            'enviados',count(*) FILTER (WHERE estado='ENVIADO'),'falhas',count(*) FILTER (WHERE estado IN ('FALHA','INCERTO')),
            'p50_s',percentile_cont(0.5) WITHIN GROUP(ORDER BY extract(epoch FROM enviado_em-criado_em)) FILTER(WHERE estado='ENVIADO'),
            'p95_s',percentile_cont(0.95) WITHIN GROUP(ORDER BY extract(epoch FROM enviado_em-criado_em)) FILTER(WHERE estado='ENVIADO'),
            'max_s',max(extract(epoch FROM enviado_em-criado_em)) FILTER(WHERE estado='ENVIADO'))
            FROM trabalhos_impressao WHERE pedido_id>{int(minimo)};"""))

    def isolar_fase(self, minimo):
        assert int(minimo) >= self.unidades["ultimo_id_inicial"]
        self.sql(f"UPDATE trabalhos_impressao SET estado='CANCELADO',erro='Final de cenário fictício' WHERE pedido_id>{int(minimo)} AND estado='PENDENTE';\nUPDATE pedidos SET status='ENTREGUE',concluido_em=now() WHERE id>{int(minimo)};")

    def proxies(self):
        subprocess.run(["docker", "build", "-f", str(ROOT / "performance/Dockerfile.rede"), "-t", "ceres-care/rede-pico:teste", str(ROOT / "performance")], check=True)
        for n in range(1, 22):
            self.dados["services"][f"rede{n:02}"] = {"image": "ceres-care/rede-pico:teste", "cpus": 0.25, "mem_limit": "64m", "cap_add": ["NET_ADMIN"],
                "environment": {"DESTINO": "frontend", "PORTA_DESTINO": "443"}, "ports": ["127.0.0.1::8080"]}
        self.salvar()
        self.comando("up", "-d", "--no-build", "--pull", "never", *[f"rede{n:02}" for n in range(1, 22)], capturar=False)
        return [f"https://127.0.0.1:{self.porta(f'rede{n:02}',8080)}" for n in range(1, 22)]

    def encerrar(self):
        assert self.projeto.startswith("ceres-carga-") and self.pasta.resolve().is_relative_to((ROOT / "work").resolve())
        self.comando("down", "--volumes", "--remove-orphans", capturar=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest="acao", required=True)
    comandos.add_parser("iniciar", help="Cria um banco fictício isolado com 21 unidades")
    encerrar = comandos.add_parser("encerrar", help="Remove somente os contêineres e o volume do laboratório informado")
    encerrar.add_argument("laboratorio", type=Path)
    args = parser.parse_args()
    if args.acao == "iniciar":
        laboratorio = Laboratorio()
        print(f"Laboratório: {laboratorio.pasta}", flush=True)
        laboratorio.iniciar()
        print(f"Pronto: {laboratorio.pasta}", flush=True)
    else:
        Laboratorio.carregar(args.laboratorio, conectar=False).encerrar()
