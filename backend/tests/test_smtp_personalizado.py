"""SMTP configurável com credenciais fictícias e coletor restrito ao loopback."""
from base64 import b64decode
import socketserver
import ssl
import threading
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from app.core.migracao_email import migrar_email
from app.schemas.email import ConfiguracaoEmailUpdate
from app.services.email_medico import ConexaoEmail, ErroEnvioEmail, autenticar_smtp, compor_mensagem, transportar_email
import test_email_medico as base


def configuracao(**alteracoes):
    return {"modo": "SMTP", "remetente": "dietas@example.com", "servidor": "smtp.exemplo.local", "porta": 587,
        "seguranca": "STARTTLS", "autenticar": True, "usuario": "conta-de-servico", "senha": "Exemplo!2026", **alteracoes}


class ConfiguracaoSmtpTest(unittest.TestCase):
    def test_smtp_aceita_senha_propria_do_ambiente_e_login_diferente_do_remetente(self):
        dados = ConfiguracaoEmailUpdate(**configuracao())
        self.assertEqual(dados.senha_app.get_secret_value(), "Exemplo!2026")
        self.assertEqual(dados.usuario, "conta-de-servico")
        self.assertNotIn("Exemplo!2026", repr(dados))

    def test_modelo_google_mantem_a_credencial_e_parametros_anteriores(self):
        with self.assertRaises(ValidationError):
            ConfiguracaoEmailUpdate(modo="GOOGLE_APP", remetente="dietas@example.com", senha="Exemplo!2026")
        dados = ConfiguracaoEmailUpdate(modo="GOOGLE_APP", remetente="dietas@example.com", senha_app="abcd efgh ijkl mnop")
        self.assertEqual(dados.senha_app.get_secret_value(), "abcdefghijklmnop")
        self.assertEqual(dados.servidor, "smtp.gmail.com")
        self.assertEqual(dados.usuario, dados.remetente)

    def test_relay_sem_tls_dispensa_senha_e_autenticacao_com_senha_exige_tls(self):
        with self.assertRaises(ValidationError):
            ConfiguracaoEmailUpdate(**configuracao(seguranca="SEM_TLS"))
        dados = configuracao(seguranca="SEM_TLS", autenticar=False, usuario=None)
        dados.pop("senha")
        self.assertFalse(ConfiguracaoEmailUpdate(**dados).autenticar)

    def test_servidores_portas_timeout_e_endereco_de_resposta_sao_validados(self):
        for alteracoes in ({"servidor": "http://smtp.local/"}, {"servidor": "smtp.local:587"}, {"porta": 0},
            {"porta": 65536}, {"tempo_limite": 31}, {"servidor_secundario": "reserva.local"},
            {"porta_secundaria": 25}, {"endereco_resposta": "a@example.com\nBcc: b@example.com"}):
            with self.subTest(alteracoes=alteracoes), self.assertRaises(ValidationError):
                ConfiguracaoEmailUpdate(**configuracao(**alteracoes))
        dados = ConfiguracaoEmailUpdate(**configuracao(servidor="192.0.2.10", servidor_secundario="reserva.local", porta_secundaria=587))
        self.assertEqual(dados.servidor_secundario, "reserva.local")

    def test_migracao_aditiva_e_idempotente_preserva_dados_e_credencial_legada(self):
        motor = create_engine("sqlite:///:memory:")
        with motor.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE configuracoes_email_unidades (filial_id INTEGER PRIMARY KEY, modo VARCHAR(20), remetente VARCHAR(254), senha_cifrada TEXT, habilitado BOOLEAN)")
            conn.exec_driver_sql("INSERT INTO configuracoes_email_unidades VALUES (1,'GOOGLE_APP','dietas@example.com','credencial-cifrada-ficticia',1)")
            migrar_email(conn); migrar_email(conn)
            self.assertIn("servidor_secundario", {c["name"] for c in inspect(conn).get_columns("configuracoes_email_unidades")})
            registro = conn.exec_driver_sql("SELECT modo,senha_cifrada,servidor FROM configuracoes_email_unidades").one()
            self.assertEqual(tuple(registro), ("GOOGLE_APP", "credencial-cifrada-ficticia", None))
        motor.dispose()


class SmtpPersonalizadoApiTest(base.EmailMedicoTest):
    async def test_salva_parametros_e_senha_generica_sem_expor_credencial(self):
        corpo = configuracao(habilitado=True, endereco_resposta="nutricao@example.com", servidor_secundario="reserva.local", porta_secundaria=587)
        r = await self.client.put(f"/api/admin/avisos-email/{self.a}/configuracao", headers=self.headers["ADMIN_TI"], json=corpo)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["servidor"], "smtp.exemplo.local")
        self.assertEqual(r.json()["usuario"], "conta-de-servico")
        self.assertEqual(r.json()["endereco_resposta"], "nutricao@example.com")
        self.assertNotIn("Exemplo!2026", r.text)
        with patch("app.api.email.transportar_email", return_value={"servidor": "smtp.exemplo.local", "porta": 587}):
            r = await self.client.post(f"/api/admin/avisos-email/{self.a}/testar", headers=self.headers["ADMIN_TI"])
        self.assertEqual(r.status_code, 200, r.text)


class TransporteSmtpPersonalizadoTest(base.TransporteEmailTest):
    def test_certificado_invalido_interrompe_sem_repetir_ou_enviar_credencial(self):
        conexao = ConexaoEmail(1, "dietas@example.com", "SMTP", "Exemplo!2026", servidor="smtp.exemplo.local", porta=465,
            seguranca="TLS", autenticar=True, usuario="servico")
        with patch("app.services.email_medico.smtplib.SMTP_SSL", side_effect=ssl.SSLCertVerificationError("fictício")), self.assertRaises(ErroEnvioEmail) as erro:
            transportar_email(conexao, self.mensagem)
        self.assertFalse(erro.exception.repetir)
        self.assertIn("certificado", str(erro.exception))

    def test_ssl_tls_usa_porta_configurada_e_valida_certificado(self):
        smtp = self.servidor()
        conexao = ConexaoEmail(1, "dietas@example.com", "SMTP", "Exemplo!2026", servidor="smtp.exemplo.local", porta=465,
            seguranca="TLS", autenticar=True, usuario="servico")
        with patch("app.services.email_medico.smtplib.SMTP_SSL", return_value=smtp) as ssl_smtp:
            transportar_email(conexao, self.mensagem)
        self.assertEqual(ssl_smtp.call_args.args, ("smtp.exemplo.local", 465))
        self.assertEqual(ssl_smtp.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        smtp.starttls.assert_not_called()
        smtp.login.assert_called_once_with("servico", "Exemplo!2026")

    def test_falha_segura_usa_secundario_e_envio_incerto_nao_faz_fallback(self):
        conexao = ConexaoEmail(1, "dietas@example.com", "SMTP", servidor="principal.local", porta=25,
            seguranca="SEM_TLS", autenticar=False, servidor_secundario="reserva.local", porta_secundaria=2525)
        smtp = self.servidor()
        with patch("app.services.email_medico.smtplib.SMTP", side_effect=[OSError("Sem conexão"), smtp]) as abrir:
            resultado = transportar_email(conexao, self.mensagem)
        self.assertEqual(resultado["servidor"], "reserva.local")
        self.assertEqual(abrir.call_args_list[1].args, ("reserva.local", 2525))
        smtp.login.assert_not_called()
        smtp.data.side_effect = OSError("Confirmação perdida")
        with patch("app.services.email_medico.smtplib.SMTP", return_value=smtp) as abrir, self.assertRaises(ErroEnvioEmail) as erro:
            transportar_email(conexao, self.mensagem)
        self.assertTrue(erro.exception.incerto)
        self.assertEqual(abrir.call_count, 1)

    def test_credencial_utf8_e_resposta_configurada(self):
        smtp = Mock(esmtp_features={"auth": "PLAIN LOGIN"})
        smtp.docmd.return_value = (235, b"OK")
        autenticar_smtp(smtp, "serviço", "Exemploá!2026")
        dados = smtp.docmd.call_args.args[1].split(" ", 1)[1]
        self.assertEqual(b64decode(dados), "\0serviço\0Exemploá!2026".encode())
        conexao = ConexaoEmail(1, "dietas@example.com", "SMTP", endereco_resposta="nutricao@example.com")
        mensagem = compor_mensagem(conexao, "medica@example.com", self.resumo, "<ficticio@example.com>")
        self.assertEqual(str(mensagem["Reply-To"]), "nutricao@example.com")

    def test_envio_smtp_real_para_coletor_local_sem_autenticacao(self):
        capturas = []
        class Coletor(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 coletor.local ESMTP\r\n")
                while linha := self.rfile.readline():
                    comando = linha.split(b" ", 1)[0].strip().upper()
                    if comando == b"DATA":
                        self.wfile.write(b"354 Envie a mensagem\r\n")
                        dados = []
                        while (parte := self.rfile.readline()) != b".\r\n":
                            if not parte: return
                            dados.append(parte)
                        capturas.append(b"".join(dados))
                    self.wfile.write(b"250 OK\r\n")
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Coletor) as servidor:
            tarefa = threading.Thread(target=servidor.serve_forever, daemon=True); tarefa.start()
            try:
                conexao = ConexaoEmail(1, "dietas@example.com", "SMTP", servidor="127.0.0.1", porta=servidor.server_address[1],
                    seguranca="SEM_TLS", autenticar=False, tempo_limite=5)
                transportar_email(conexao, self.mensagem)
            finally:
                servidor.shutdown(); tarefa.join(timeout=2)
        self.assertEqual(len(capturas), 1)
        self.assertIn(b"multipart/alternative", capturas[0])
