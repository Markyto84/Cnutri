"""Prepara somente o banco descartável cujo ambiente declara SIMULACAO_PICO=1."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, "/app")

from jose import jwt
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_senha
from app.models.models import Dieta, Filial, FormularioConfig, Perfil, SessaoCopeira, SessaoUsuario, Usuario


async def principal():
    assert os.environ.get("SIMULACAO_PICO") == "1" and settings.URL_PUBLICA == "https://carga.invalid"
    esquemas = json.loads(Path("/config/formularios.json").read_text(encoding="utf-8"))["formularios"]
    agora = datetime.utcnow()
    saida = {"unidades": [], "versao_imagem": "0.1.0"}
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Filial)) <= 1
        assert await db.scalar(text("SELECT count(*) FROM pedidos")) == 0
        perfil = await db.scalar(select(Perfil).where(Perfil.nome == "COPEIRA"))
        senha_hash = hash_senha("PicoTeste@12")
        for numero in range(1, 22):
            filial = await db.scalar(select(Filial).limit(1)) if numero == 1 else None
            if filial is None:
                filial = Filial()
                db.add(filial)
            filial.nome = f"SIMULAÇÃO DE CARGA — Unidade {numero:02}"
            filial.codigo_slug = f"simulacao-pico-{numero:02}"
            filial.ativa = True
            filial.ip_impressora = os.environ["IMPRESSORA_SIMULADA_IP"]
            await db.flush()
            dieta = await db.scalar(select(Dieta).where(Dieta.filial_id == filial.id, func.upper(Dieta.nome) == "GERAL"))
            if dieta is None:
                dieta = Dieta(filial_id=filial.id, nome="GERAL")
                db.add(dieta)
            dieta.nome, dieta.ativa = "GERAL", True
            await db.flush()
            for tipo, esquema in esquemas.items():
                config = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == filial.id, FormularioConfig.tipo_publico == tipo))
                if config is None:
                    config = FormularioConfig(filial_id=filial.id, tipo_publico=tipo)
                    db.add(config)
                config.esquema_json = deepcopy(esquema)
            tokens = []
            for n in range(5):
                usuario = Usuario(nome=f"Copeira FICTÍCIA {numero:02}-{n+1}", nome_usuario=f"pico_{numero:02}_{n+1}",
                    perfil_id=perfil.id, senha_hash=senha_hash, filiais=[filial], ativo=True, troca_senha_obrigatoria=False)
                db.add(usuario)
                await db.flush()
                jti = str(uuid4())
                db.add(SessaoUsuario(id=jti, usuario_id=usuario.id, expira_em=agora + timedelta(hours=6)))
                db.add(SessaoCopeira(id=jti, usuario_id=usuario.id, filial_id=filial.id, presenca_ate=agora + timedelta(minutes=3)))
                token = jwt.encode({"sub": str(usuario.id), "perfil": "COPEIRA", "nome": usuario.nome, "exp": agora + timedelta(hours=6), "jti": jti}, settings.JWT_SECRET, algorithm="HS256")
                tokens.append(token)
            grupos = next(c["grupos"] for c in esquemas["ENFERMAGEM"]["campos"] if c["id"] == "cardapio")
            cardapio = next(g["opcoes"][0] for g in grupos if "GERAL" in [d.upper() for d in g["dietas"]])
            refeicao = next(c["opcoes"][0] for c in esquemas["MEDICO"]["campos"] if c["id"] == "refeicao")
            paciente = {"tipo_solicitacao": "PACIENTE", "solicitante_identificacao": "COREN SIMULACAO", "solicitante_nome": "Solicitante fictício",
                "nome_paciente": "PACIENTE FICTÍCIO DE TESTE", "prontuario": "SIMULACAO-CARGA", "leito": "TESTE-01", "dieta_id": dieta.id, "observacoes_alergias": "SIMULAÇÃO DE CARGA — sem uso assistencial.",
                "dados_dinamicos": {"andar": "TÉRREO - OBSERVAÇÃO", "internado_mais_6h": "Não", "matricula": "TESTE", "data_nascimento": "1970-01-01", "sexo": "FEMININO", "refeicao": "ALMOÇO", "para": "Paciente", "cardapio": cardapio, "liquido_espessado": "Não"}}
            medico = {"tipo_solicitacao": "MEDICO", "solicitante_identificacao": "CRM SIMULACAO", "solicitante_nome": "Médico fictício", "observacoes_alergias": "SIMULAÇÃO DE CARGA — sem uso assistencial.",
                "dados_dinamicos": {"equipe": "Médica", "horario_entrega": "12:30", "refeicao": refeicao, "suco": "COM SUCO", "sobremesa": "SOBREMESA DO DIA", "local_entrega": "TÉRREO - CONFORTO MÉDICO"}}
            saida["unidades"].append({"id": filial.id, "slug": filial.codigo_slug, "dieta_id": dieta.id, "tokens": tokens, "paciente": paciente, "medico": medico})
        await db.commit()
    print("Gerando histórico sintético de 1 ano e 100 refeições ativas por unidade...", flush=True)
    async with SessionLocal() as db:
        for quantidade, ativo in ((36500, False), (100, True)):
            await db.execute(text("""INSERT INTO pedidos
                (filial_id,tipo_solicitacao,solicitante_identificacao,solicitante_nome,nome_paciente,leito,dieta_id,
                 observacoes_alergias,status,dados_dinamicos,criado_em,concluido_em,versao)
                SELECT f.id,'PACIENTE','REGISTRO FICTICIO','Solicitante simulado','PACIENTE FICTICIO','TESTE',d.id,
                  'DADOS FICTICIOS PARA TESTE DE CARGA',
                  CASE WHEN :ativo THEN CASE WHEN n % 4=0 THEN 'PRONTO' WHEN n%4=1 THEN 'EM_PREPARO' ELSE 'PENDENTE' END ELSE 'ENTREGUE' END,
                  CAST(:dados AS jsonb),
                  CASE WHEN :ativo THEN now() ELSE now() - ((n % 365)+1) * interval '1 day' END,
                  CASE WHEN :ativo THEN NULL ELSE now() - (n%365) * interval '1 day' END,1
                FROM filiais f JOIN dietas d ON d.filial_id=f.id AND d.nome='GERAL'
                CROSS JOIN generate_series(1,:quantidade) n WHERE f.codigo_slug LIKE 'simulacao-pico-%'
            """), {"ativo": ativo, "dados": json.dumps(saida["unidades"][0]["paciente"]["dados_dinamicos"], ensure_ascii=False), "quantidade": quantidade})
            await db.commit()
        await db.execute(text("""INSERT INTO trabalhos_impressao
            (pedido_id,tipo_documento,estado,tentativas,criado_em,proxima_tentativa_em,iniciado_em,enviado_em)
            SELECT id,'FILIPETA','ENVIADO',1,criado_em,criado_em,criado_em,criado_em+interval '2 seconds' FROM pedidos"""))
        await db.commit()
        await db.execute(text("ANALYZE pedidos"))
        await db.execute(text("ANALYZE trabalhos_impressao"))
        await db.commit()
        saida["ultimo_id_inicial"] = await db.scalar(text("SELECT max(id) FROM pedidos"))
        saida["historicos"] = await db.scalar(text("SELECT count(*) FROM pedidos WHERE status='ENTREGUE'"))
        saida["ativos_iniciais"] = await db.scalar(text("SELECT count(*) FROM pedidos WHERE status <> 'ENTREGUE'"))
        saida["banco_bytes"] = await db.scalar(text("SELECT pg_database_size(current_database())"))
    Path("/resultados/unidades-privado.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print("21 unidades e 105 sessões fictícias preparadas; credenciais mantidas no arquivo privado.", flush=True)


if __name__ == "__main__":
    asyncio.run(principal())
