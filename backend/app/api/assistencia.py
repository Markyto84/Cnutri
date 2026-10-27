"""Consulta, conferência do vínculo e correções com histórico por unidade."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..core.ws import gerenciador_ws
from ..models.models import EntregaPedido, EventoAssistencial, FormularioConfig, HistoricoPedido, Pedido, RecebimentoEntrega, RecebimentoQR, TrabalhoImpressao, Usuario
from ..schemas.schemas import ConferenciaPrescricao, PedidoAssistencialUpdate, PedidoOut
from ..services.assistencia import CAMPOS_PEDIDO, referencia_informada, registrar_evento, retrato, validar_referencia
from ..services.fila_impressao import enfileirar
from ..services.formulario_paciente import formulario_paciente
from ..services.liquido_espessado import formulario_liquidos
from ..services.operacao import data_utc
from ..services.validacao_pedidos import validar_pedido

router = APIRouter(prefix="/api/assistencia", tags=["Prescrições e rastreabilidade"])
GESTORES = exigir_perfis("NUTRICIONISTA", "ADMIN_TI")


async def obter(db, pedido_id, usuario, bloquear=False):
    consulta = select(Pedido).options(selectinload(Pedido.dieta), selectinload(Pedido.filial)).where(Pedido.id == pedido_id)
    if bloquear:
        consulta = consulta.with_for_update(of=Pedido)
    pedido = await db.scalar(consulta)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    await verificar_acesso_filial(pedido.filial_id, usuario, db)
    return pedido


@router.get("/pedidos")
async def listar(filial_id: int, response: Response, busca: str = Query("", max_length=100),
    pagina: int = Query(1, ge=1), db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTORES)):
    await verificar_acesso_filial(filial_id, usuario, db)
    filtros = [Pedido.filial_id == filial_id, Pedido.tipo_solicitacao == "PACIENTE"]
    if busca.strip():
        termo = "%" + busca.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        opcoes = [Pedido.nome_paciente.ilike(termo, escape="\\"), Pedido.prontuario.ilike(termo, escape="\\")]
        if busca.strip().lstrip("#").isdigit() and int(busca.strip().lstrip("#")) <= 2147483647:
            opcoes.append(Pedido.id == int(busca.strip().lstrip("#")))
        filtros.append(or_(*opcoes))
    total = await db.scalar(select(func.count(Pedido.id)).where(*filtros))
    pedidos = (await db.scalars(select(Pedido).options(selectinload(Pedido.dieta)).where(*filtros)
        .order_by(Pedido.criado_em.desc(), Pedido.id.desc()).offset((pagina - 1) * 25).limit(25))).all()
    response.headers["Cache-Control"] = "private, no-store"
    return {"total": total, "pagina": pagina, "itens": [PedidoOut.model_validate(p).model_dump(mode="json") for p in pedidos]}


@router.get("/pedidos/{pedido_id}")
async def detalhes(pedido_id: int, response: Response, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTORES)):
    pedido = await obter(db, pedido_id, usuario)
    eventos = (await db.scalars(select(EventoAssistencial).where(EventoAssistencial.pedido_id == pedido.id)
        .order_by(EventoAssistencial.id))).all()
    # Registros antigos não ganham autores, prescrições ou conferências presumidos.
    historico = (await db.execute(select(HistoricoPedido, Usuario.nome).outerjoin(Usuario,
        Usuario.id == HistoricoPedido.alterado_por_usuario_id).where(HistoricoPedido.pedido_id == pedido.id)
        .order_by(HistoricoPedido.data_hora, HistoricoPedido.id))).all()
    entrega = await db.get(EntregaPedido, pedido.id)
    recebimento = await db.get(RecebimentoEntrega, pedido.id) if entrega else None
    qr = await db.get(RecebimentoQR, pedido.id)
    config = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == pedido.filial_id,
        FormularioConfig.tipo_publico == "ENFERMAGEM"))
    emitidos = await db.scalar(select(TrabalhoImpressao.id).where(TrabalhoImpressao.pedido_id == pedido.id,
        TrabalhoImpressao.estado.in_(("ENVIADO", "INCERTO"))).limit(1))
    response.headers["Cache-Control"] = "private, no-store"
    return {"pedido": PedidoOut.model_validate(pedido).model_dump(mode="json"),
        "formulario": formulario_paciente(formulario_liquidos(config.esquema_json)) if config else None,
        "documentos_emitidos": emitidos is not None,
        "eventos": [{"id": e.id, "acao": e.acao, "autor_usuario_id": e.autor_usuario_id,
            "autor_nome": e.autor_nome, "autor_perfil": e.autor_perfil, "motivo": e.motivo,
            "antes": e.antes, "depois": e.depois, "criado_em": data_utc(e.criado_em)} for e in eventos],
        "etapas": [{"anterior": h.status_anterior, "nova": h.status_novo, "usuario_id": h.alterado_por_usuario_id,
            "nome_atual_usuario": nome, "data_hora": data_utc(h.data_hora)} for h, nome in historico],
        "entrega": {"copeira_id": entrega.copeira_id, "copeira_nome": entrega.copeira_nome,
            "registrado_por_usuario_id": entrega.registrado_por_usuario_id, "entregue_em": data_utc(entrega.entregue_em),
            "recebedor_nome": recebimento.recebedor_nome if recebimento else None,
            "assinatura_registrada": recebimento is not None, "origem_entrega": 'Copeira'} if entrega else {
                "copeira_id": None, "copeira_nome": None, "registrado_por_usuario_id": None,
                "recebedor_nome": None, "recebedor_registro_profissional": qr.registro_profissional,
                "entregue_em": data_utc(qr.confirmado_em), "assinatura_registrada": False,
                "origem_entrega": 'QR Code'} if qr and qr.confirmado_em else None}


@router.put("/pedidos/{pedido_id}")
async def corrigir(pedido_id: int, dados: PedidoAssistencialUpdate, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTORES)):
    pedido = await obter(db, pedido_id, usuario, bloquear=True)
    if not pedido.filial.ativa:
        raise HTTPException(409, "A unidade está inativa. Seu histórico permanece disponível para consulta")
    if pedido.versao != dados.versao:
        raise HTTPException(409, "O pedido foi alterado. Atualize e confira os dados antes de salvar")
    if pedido.tipo_solicitacao != "PACIENTE" or dados.pedido.tipo_solicitacao != "PACIENTE":
        raise HTTPException(422, "Esta correção é exclusiva para o formulário do paciente")
    if pedido.status not in ("PENDENTE", "EM_PREPARO", "PRONTO"):
        raise HTTPException(409, "Pedidos entregues ou cancelados mantêm seus registros originais")
    for campo in ("solicitante_nome", "solicitante_identificacao"):
        if getattr(dados.pedido, campo) != getattr(pedido, campo):
            raise HTTPException(422, "A identificação do solicitante original deve ser preservada")
    validar_referencia(dados.pedido)
    dieta = await validar_pedido(db, pedido.filial_id, dados.pedido)
    trabalhos = (await db.scalars(select(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == pedido.id).with_for_update())).all()
    if any(t.estado == "PROCESSANDO" for t in trabalhos):
        raise HTTPException(409, "Há uma impressão em andamento. Aguarde a conclusão antes de corrigir")
    if any(t.estado in ("ENVIADO", "INCERTO") for t in trabalhos) and not dados.confirmar_substituicao:
        raise HTTPException(409, "Confirme a substituição das filipetas e etiquetas anteriores com a cozinha")
    antes = retrato(pedido)
    # O formulário atual omite este campo. Sua ausência preserva o dado anterior.
    nova_referencia = referencia_informada(dados.pedido) if "prescricao" in dados.pedido.model_fields_set else pedido.prescricao
    proposto = {c: getattr(dados.pedido, c) for c in CAMPOS_PEDIDO}
    referencia_atual = {k: (pedido.prescricao or {}).get(k) for k in ("referencia", "data_hora", "prescritor_nome", "prescritor_registro")} if pedido.prescricao else None
    referencia_nova = {k: nova_referencia.get(k) for k in ("referencia", "data_hora", "prescritor_nome", "prescritor_registro")} if nova_referencia else None
    if all(antes[c] == v for c, v in proposto.items()) and referencia_atual == referencia_nova:
        raise HTTPException(422, "Nenhuma informação foi alterada")
    for campo, valor in proposto.items():
        setattr(pedido, campo, valor)
    pedido.dieta = dieta
    pedido.prescricao = nova_referencia
    pedido.versao += 1
    pedido.status, pedido.concluido_em = "PENDENTE", None
    for trabalho in trabalhos:
        if trabalho.estado in ("PENDENTE", "FALHA"):
            trabalho.estado, trabalho.erro = "CANCELADO", "Documento substituído após correção do pedido"
    await db.flush()
    registrar_evento(db, pedido, "PEDIDO_CORRIGIDO", usuario, antes, retrato(pedido), dados.motivo)
    if antes["status"] != "PENDENTE":
        db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior=antes["status"], status_novo="PENDENTE", alterado_por_usuario_id=usuario.id))
    await enfileirar(db, pedido, pedido.filial, usuario.id, confirmar=dados.confirmar_substituicao)
    await db.commit()
    await db.refresh(pedido, attribute_names=["trabalhos_impressao", "recebimento_qr"])
    await gerenciador_ws.transmitir(pedido.filial_id, {"evento": "pedido_corrigido", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json")})
    return {"id": pedido.id, "versao": pedido.versao, "mensagem": "Correção registrada. Pedido devolvido a Pendentes; substitua os documentos anteriores com a cozinha."}


@router.post("/pedidos/{pedido_id}/conferencia")
async def conferir(pedido_id: int, dados: ConferenciaPrescricao, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTORES)):
    pedido = await obter(db, pedido_id, usuario, bloquear=True)
    if not pedido.filial.ativa:
        raise HTTPException(409, "A unidade está inativa")
    if pedido.versao != dados.versao:
        raise HTTPException(409, "O pedido foi alterado. Atualize antes de conferir")
    if not pedido.prescricao or pedido.status not in ("PENDENTE", "EM_PREPARO", "PRONTO"):
        raise HTTPException(409, "A conferência exige referência informada em um pedido ativo")
    if pedido.prescricao.get("situacao") == "CONFERIDA":
        return {"id": pedido.id, "versao": pedido.versao}
    antes = retrato(pedido)
    pedido.prescricao = {**pedido.prescricao, "situacao": "CONFERIDA", "conferida_por_usuario_id": usuario.id,
        "conferida_por_nome": usuario.nome, "conferida_em": datetime.now(timezone.utc).isoformat()}
    pedido.versao += 1
    registrar_evento(db, pedido, "VINCULO_CONFERIDO", usuario, antes, retrato(pedido))
    codigo_qr = await db.get(RecebimentoQR, pedido.id)
    if codigo_qr:
        codigo_qr.versao = pedido.versao
    await db.commit()
    return {"id": pedido.id, "versao": pedido.versao}
