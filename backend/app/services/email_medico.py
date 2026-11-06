"""Aviso de refeição médica: resumo congelado na saída e transporte SMTP com TLS."""
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from html import escape
import json
import smtplib
import ssl

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import undefer

from ..core.config import settings
from ..models.models import ConfiguracaoEmailUnidade, FormularioConfig
from .endereco_email import normalizar_email
from .impressora import ROTULOS_PADRAO, _formatar_valor

SERVIDORES = {"GOOGLE_APP": "smtp.gmail.com", "GOOGLE_RELAY": "smtp-relay.gmail.com"}
CAMPOS_RESUMO = ("equipe", "horario_entrega", "refeicao", "cardapio", "suco", "sobremesa", "local_entrega", "observacoes_alergias")


def cifra():
    if not settings.EMAIL_CREDENCIAIS_CHAVE:
        raise HTTPException(503, "A TI precisa preparar a proteção das credenciais de e-mail neste servidor")
    return Fernet(settings.EMAIL_CREDENCIAIS_CHAVE.encode("ascii"))


def cifrar_senha(filial_id, senha):
    return cifra().encrypt(json.dumps({"filial_id": filial_id, "senha": senha}).encode()).decode("ascii")


def decifrar_senha(filial_id, valor):
    try:
        dados = json.loads(cifra().decrypt(valor.encode("ascii")))
        if dados["filial_id"] != filial_id:
            raise ValueError()
        return dados["senha"]
    except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, "Não foi possível abrir a credencial desta unidade. Confira a chave privada ou recadastre a senha de app") from None


@dataclass(repr=False)
class ConexaoEmail:
    filial_id: int
    remetente: str
    modo: str
    senha: str | None = field(default=None, repr=False)


async def obter_conexao(db, filial_id, *, exigir_habilitado=True):
    config = await db.scalar(select(ConfiguracaoEmailUnidade).options(undefer(ConfiguracaoEmailUnidade.senha_cifrada))
        .where(ConfiguracaoEmailUnidade.filial_id == filial_id))
    if not config or exigir_habilitado and not config.habilitado:
        raise HTTPException(409, "Os avisos por e-mail estão desativados nesta unidade")
    senha = None
    if config.modo == "GOOGLE_APP":
        if not config.senha_cifrada:
            raise HTTPException(409, "Cadastre a senha de app do Google desta unidade")
        senha = decifrar_senha(filial_id, config.senha_cifrada)
    return ConexaoEmail(filial_id, normalizar_email(config.remetente), config.modo, senha)


async def resumir_pedido(db, pedido, filial):
    config = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == pedido.filial_id,
        FormularioConfig.tipo_publico == "MEDICO"))
    campos = {c["id"]: c for c in (config.esquema_json if config else {}).get("campos", []) if isinstance(c, dict) and "id" in c}
    valores = {**(pedido.dados_dinamicos or {}), "observacoes_alergias": pedido.observacoes_alergias}
    itens = []
    for chave in CAMPOS_RESUMO:
        valor = valores.get(chave)
        if valor is None or isinstance(valor, str) and not valor.strip() or valor == []:
            continue
        itens.append([campos.get(chave, {}).get("rotulo") or ROTULOS_PADRAO[chave], _formatar_valor(valor)])
    if not valores.get("refeicao") and not valores.get("cardapio") and pedido.dieta:
        itens.insert(0, ["Refeição / Dieta", pedido.dieta.nome])
    return {"pedido_id": pedido.id, "unidade": filial.nome, "solicitante": pedido.solicitante_nome or "Profissional",
        "itens": itens, "pronto_em": datetime.now(timezone.utc).isoformat()}


def compor_corpos(resumo):
    pedido = resumo["pedido_id"]
    saudacao = f'Olá, {resumo["solicitante"]}!'
    aviso = "Sua refeição saiu para entrega e está a caminho do local solicitado."
    instante = datetime.fromisoformat(resumo["pronto_em"]).astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    itens = [["Unidade", resumo["unidade"]], *resumo["itens"]]
    texto = f"Cnutri · Pedido #{pedido}\n\n{saudacao}\n\n{aviso}\n\nResumo da sua solicitação\n"
    texto += "\n".join(f"{rotulo}: {valor}" for rotulo, valor in itens)
    texto += f"\n\nSaída registrada em {instante} (horário de Brasília).\nCuidado em cada etapa, da solicitação à entrega.\n"
    linhas = "".join(f'<tr><th scope="row" style="padding:12px 16px;text-align:left;vertical-align:top;color:#475569;border-bottom:1px solid #e2e8f0;width:36%;font-weight:600">{escape(str(rotulo))}</th>'
        f'<td style="padding:12px 16px;color:#172b3a;border-bottom:1px solid #e2e8f0;word-break:break-word">{escape(str(valor)).replace(chr(10), "<br>")}</td></tr>' for rotulo, valor in itens)
    html = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cnutri · Sua refeição está a caminho</title></head>
<body style="margin:0;padding:24px 12px;background:#edf5f8;font-family:Arial,Helvetica,sans-serif;color:#172b3a">
<table role="presentation" width="100%" style="width:100%;max-width:600px;table-layout:fixed;margin:0 auto;border-collapse:collapse;background:white;border-radius:16px;overflow:hidden"><tr><td style="padding:24px;background:#0070AD;color:white"><p style="margin:0;font-size:26px;font-weight:bold">Cnutri</p><p style="margin:8px 0 0;font-size:14px">Cuidado em cada etapa</p></td></tr>
<tr><td style="padding:28px 24px 12px"><p style="margin:0 0 12px">{escape(saudacao)}</p><h1 style="margin:0 0 14px;font-size:26px;line-height:1.3;color:#0070AD">Sua refeição está a caminho.</h1><p style="margin:0;line-height:1.6">{aviso}</p><p style="margin:20px 0 12px;font-weight:bold">Resumo da sua solicitação · Pedido #{pedido}</p></td></tr>
<tr><td style="padding:0 24px"><table width="100%" aria-label="Resumo da refeição" style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:14px;line-height:1.5;background:#f7fafc">{linhas}</table></td></tr>
<tr><td style="padding:20px 24px 28px;font-size:12px;line-height:1.6;color:#526574">Saída registrada em {instante} (horário de Brasília).<br>Cuidado em cada etapa, da solicitação à entrega.</td></tr></table></body></html>'''
    return texto, html


def compor_mensagem(conexao, destinatario, resumo, mensagem_id):
    mensagem = EmailMessage(policy=SMTP)
    mensagem["From"] = f'Cnutri <{normalizar_email(conexao.remetente)}>'
    mensagem["To"] = normalizar_email(destinatario)
    mensagem["Subject"] = f'Cnutri · Sua refeição está a caminho · Pedido #{int(resumo["pedido_id"])}'
    mensagem["Message-ID"] = mensagem_id
    mensagem["Date"] = format_datetime(datetime.fromisoformat(resumo["pronto_em"]))
    texto, html = compor_corpos(resumo)
    mensagem.set_content(texto, charset="utf-8")
    mensagem.add_alternative(html, subtype="html", charset="utf-8")
    return mensagem


class ErroEnvioEmail(Exception):
    def __init__(self, mensagem, *, repetir=False, incerto=False):
        self.mensagem, self.repetir, self.incerto = mensagem, repetir, incerto
        super().__init__(mensagem)


def transportar_email(conexao, mensagem=None):
    """Sem mensagem, verifica TLS/autenticação sem enviar e-mail a ninguém."""
    smtp = None
    dados_iniciados = False
    try:
        smtp = smtplib.SMTP(SERVIDORES[conexao.modo], 587, timeout=5)
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        if conexao.modo == "GOOGLE_APP":
            smtp.login(conexao.remetente, conexao.senha)
        if mensagem is None:
            codigo, _ = smtp.noop()
            if codigo != 250:
                raise ErroEnvioEmail("O Google não confirmou a conexão. Confira a configuração da unidade", repetir=True)
            return
        codigo, _ = smtp.mail(conexao.remetente)
        if codigo != 250:
            raise ErroEnvioEmail("O Google recusou o remetente desta unidade", repetir=400 <= codigo < 500)
        codigo, _ = smtp.rcpt(str(mensagem["To"]))
        if codigo not in (250, 251):
            raise ErroEnvioEmail("O servidor recusou o e-mail do destinatário", repetir=400 <= codigo < 500)
        dados_iniciados = True
        codigo, _ = smtp.data(mensagem.as_bytes())
        if codigo != 250:
            raise ErroEnvioEmail("O servidor não aceitou a mensagem", repetir=400 <= codigo < 500)
    except smtplib.SMTPAuthenticationError:
        raise ErroEnvioEmail("Autenticação recusada. Confira a senha de app e as permissões do Google Workspace") from None
    except smtplib.SMTPResponseException as exc:
        raise ErroEnvioEmail("O Google recusou temporariamente o envio" if 400 <= exc.smtp_code < 500 else "O Google recusou a conexão ou o envio",
            repetir=400 <= exc.smtp_code < 500) from None
    except (OSError, smtplib.SMTPServerDisconnected):
        raise ErroEnvioEmail("A conexão foi interrompida após iniciar o envio; confira antes de reenviar" if dados_iniciados else "Sem conexão com o serviço de e-mail",
            repetir=not dados_iniciados, incerto=dados_iniciados) from None
    except smtplib.SMTPException:
        raise ErroEnvioEmail("O serviço de e-mail não disponibilizou a conexão segura necessária") from None
    finally:
        if smtp is not None:
            # Fechar a conexão não pode transformar uma mensagem já aceita em falha.
            with suppress(Exception):
                smtp.close()
