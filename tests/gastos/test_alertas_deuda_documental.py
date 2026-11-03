"""Pruebas exhaustivas para la política de advertencias visuales y control de deuda (Issue #93).

Cubre:
- GAST-R07: Parámetros canónicos DIAS_GRACIA_RENDICION_FACTURA = 15
  y MAX_TRAMITES_MORA_PERMITIDOS = 2.
- Inyección de fecha_referencia en verificar_deuda_documental_solicitante y crear_solicitud_gasto.
- Aislamiento por modalidad: REINTEGRO nunca adeuda factura post-pago;
  COMPRA_DIRECTA con factura inicial no adeuda.
- Escalado determinista:
  - 1 trámite dentro del plazo de gracia (<= 15 días): advertencia preventiva en UI, alta permitida.
  - Límite de 15 días: dentro del plazo de gracia.
  - 16 días: entra en mora (dias > 15), pero 1 o 2 trámites en mora no bloquean (<= 2).
  - 3 trámites en mora (> 2): bloqueo estricto con DeudaDocumentalBloqueoError.
- Ciclo de vida documental:
  - Desbloqueo al incorporar FACTURA_PROVEEDOR válida.
  - Rechazo de factura (RevisionDocumento.RECHAZADO) no cancela la deuda y mantiene el bloqueo.
  - Reemplazo de factura rechazada desbloquea al solicitante.
- Ergonomía visual:
  - Banner preventivo (message-warning) en listado y formulario de alta.
  - Banner de bloqueo crítico (message-error) y deshabilitación de envío en formulario de alta.
  - Rechazo de POST con HTTP 400 cuando el solicitante se encuentra bloqueado.
- Aislamiento entre solicitantes: la deuda de un usuario no afecta a otro.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from documentos.models import Documento, RevisionDocumento
from gastos.models import EstadoSolicitud, PagoExterno, SolicitudGasto, TipoFlujoGasto
from gastos.services import (
    DIAS_GRACIA_RENDICION_FACTURA,
    MAX_TRAMITES_MORA_PERMITIDOS,
    DeudaDocumentalBloqueoError,
    crear_solicitud_gasto,
    verificar_deuda_documental_solicitante,
)
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# Helpers para configuración de escenarios sintéticos
# ---------------------------------------------------------------------------


def _crear_compra_directa_pagada(
    solicitante: Any,
    concepto: str,
    fecha_pago: date,
    importe: Decimal = Decimal("50000.00"),
    con_factura_inicial: bool = False,
) -> SolicitudGasto:
    """Crea una SolicitudGasto de COMPRA_DIRECTA aceptada y con PagoExterno registrado."""
    solicitud = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto=concepto,
        monto_estimado=importe,
        estado=EstadoSolicitud.ACEPTADA,
    )
    solicitud.tipo_flujo = TipoFlujoGasto.COMPRA_DIRECTA
    solicitud.save(update_fields=["tipo_flujo"])

    ref_doc = f"doc-ref-{uuid.uuid4().hex[:8]}"
    PagoExterno.objects.create(
        solicitud=solicitud,
        importe=importe,
        moneda="ARS",
        fecha_pago=fecha_pago,
        referencia_externa=f"TRF-{uuid.uuid4().hex[:6].upper()}",
        referencia_documental=ref_doc,
        huella_idempotencia=uuid.uuid4().hex,
        monto_bruto=importe,
        monto_retencion_atp=Decimal("0.00"),
        referencia_atp="",
    )

    if con_factura_inicial:
        _adjuntar_factura(solicitud, solicitante)

    return solicitud


def _adjuntar_factura(
    solicitud: SolicitudGasto,
    autor: Any,
    reemplaza: Documento | None = None,
) -> Documento:
    """Adjunta un Documento de tipo FACTURA_PROVEEDOR a la solicitud."""
    serie = reemplaza.serie if reemplaza else uuid.uuid4()
    version = (reemplaza.version + 1) if reemplaza else 1
    doc = Documento.objects.create(
        solicitud_gasto=solicitud,
        tramite_base=solicitud.tramite_base,
        serie=serie,
        version=version,
        reemplaza=reemplaza,
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
        archivo=f"documentos/factura-{uuid.uuid4().hex}.pdf",
        nombre_original="factura-oficial.pdf",
        formato="pdf",
        tamano=2048,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        autor=autor,
    )
    return doc


# ---------------------------------------------------------------------------
# 1. Parámetros Canónicos y Casos Base
# ---------------------------------------------------------------------------


def test_constantes_canonicas_deuda_documental() -> None:
    """Verifica que los parámetros en código coincidan con la especificación GAST-R07."""
    assert DIAS_GRACIA_RENDICION_FACTURA == 15
    assert MAX_TRAMITES_MORA_PERMITIDOS == 2


def test_solicitante_sin_solicitudes_resumen_vacio(create_actor: Any) -> None:
    """Un solicitante nuevo sin trámites no registra deuda ni bloqueo."""
    user, _ = create_actor("solic_limpio", ["gastos.presentar"])
    resumen = verificar_deuda_documental_solicitante(user)

    assert resumen.total_pendientes == 0
    assert resumen.total_en_mora == 0
    assert not resumen.tiene_deuda
    assert not resumen.tiene_bloqueo
    assert resumen.solicitudes_pendientes == ()
    assert resumen.solicitudes_en_mora == ()


def test_reintegro_pagado_no_genera_deuda_documental(create_actor: Any) -> None:
    """Los reintegros pagados quedan saldados y nunca generan deuda documental (GAST-R03)."""
    user, _ = create_actor("docente_reintegro", ["gastos.presentar"])
    solicitud = crear_gasto_sintetico(
        solicitante=user,
        concepto="Reintegro pasajes congreso",
        monto_estimado=Decimal("35000.00"),
        estado=EstadoSolicitud.ACEPTADA,
    )
    solicitud.tipo_flujo = TipoFlujoGasto.REINTEGRO
    solicitud.save(update_fields=["tipo_flujo"])

    # Pago registrado hace 60 días
    PagoExterno.objects.create(
        solicitud=solicitud,
        importe=Decimal("35000.00"),
        moneda="ARS",
        fecha_pago=date(2026, 9, 1),
        referencia_externa="TRF-REINT-99",
        referencia_documental="doc-reintegro-factura",
        huella_idempotencia="r" * 64,
        monto_bruto=Decimal("35000.00"),
        monto_retencion_atp=Decimal("0.00"),
    )

    resumen = verificar_deuda_documental_solicitante(
        user, fecha_referencia=date(2026, 11, 3)
    )
    assert resumen.total_pendientes == 0
    assert not resumen.tiene_deuda
    assert not resumen.tiene_bloqueo


def test_compra_directa_con_factura_inicial_no_genera_deuda(create_actor: Any) -> None:
    """Una compra directa pagada contra factura inicial ya cuenta con comprobante definitivo."""
    user, _ = create_actor("solic_fac_inicial", ["gastos.presentar"])
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Herramientas de laboratorio",
        fecha_pago=date(2026, 10, 1),
        con_factura_inicial=True,
    )

    resumen = verificar_deuda_documental_solicitante(
        user, fecha_referencia=date(2026, 11, 3)
    )
    assert resumen.total_pendientes == 0
    assert not resumen.tiene_deuda
    assert not resumen.tiene_bloqueo


# ---------------------------------------------------------------------------
# 2. Plazo de Gracia y Escalado Determinista de Mora
# ---------------------------------------------------------------------------


def test_compra_directa_dentro_plazo_gracia_genera_aviso_sin_bloqueo(create_actor: Any) -> None:
    """1 trámite pagado hace 10 días (< 15): muestra advertencia pero permite nueva solicitud."""
    user, actor = create_actor("solic_gracia", ["gastos.presentar"])
    fecha_pago = date(2026, 10, 20)
    solicitud = _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Insumos de oficina recientes",
        fecha_pago=fecha_pago,
    )

    fecha_eval = date(2026, 10, 30)  # 10 días transcurridos
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)

    assert resumen.total_pendientes == 1
    assert resumen.total_en_mora == 0
    assert resumen.tiene_deuda is True
    assert resumen.tiene_bloqueo is False

    detalle = resumen.solicitudes_pendientes[0]
    assert detalle.solicitud_id == solicitud.pk
    assert detalle.dias_transcurridos == 10
    assert detalle.en_mora is False

    # El servicio de creación permite crear solicitudes sin lanzar excepción
    nueva = crear_solicitud_gasto(
        actor=actor,
        concepto="Nueva solicitud autorizada",
        monto_estimado=Decimal("12000.00"),
        unidad_requirente="Laboratorio",
        fecha_referencia=fecha_eval,
    )
    assert nueva.pk is not None


def test_borde_exacto_dia_15_no_es_mora(create_actor: Any) -> None:
    """Exactamente a los 15 días del pago, el trámite sigue dentro del plazo de gracia."""
    user, actor = create_actor("solic_borde_15", ["gastos.presentar"])
    fecha_pago = date(2026, 10, 1)
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra al día 15",
        fecha_pago=fecha_pago,
    )

    fecha_eval = date(2026, 10, 16)  # 15 días exactos
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)

    assert resumen.total_pendientes == 1
    assert resumen.total_en_mora == 0
    assert resumen.tiene_bloqueo is False
    assert resumen.solicitudes_pendientes[0].en_mora is False


def test_dia_16_entra_en_mora_pero_1_tramite_no_bloquea(create_actor: Any) -> None:
    """Al día 16 el trámite pasa a mora, pero 1 trámite no supera el umbral de 2."""
    user, actor = create_actor("solic_mora_uno", ["gastos.presentar"])
    fecha_pago = date(2026, 10, 1)
    solicitud = _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra vencida por 1 día",
        fecha_pago=fecha_pago,
    )

    fecha_eval = date(2026, 10, 17)  # 16 días
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)

    assert resumen.total_pendientes == 1
    assert resumen.total_en_mora == 1
    assert resumen.tiene_deuda is True
    assert resumen.tiene_bloqueo is False  # 1 <= 2

    detalle = resumen.solicitudes_en_mora[0]
    assert detalle.solicitud_id == solicitud.pk
    assert detalle.dias_transcurridos == 16
    assert detalle.en_mora is True

    # Creación todavía permitida
    nueva = crear_solicitud_gasto(
        actor=actor,
        concepto="Solicitud con 1 mora permitida",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Dpto",
        fecha_referencia=fecha_eval,
    )
    assert nueva.pk is not None


def test_dos_tramites_en_mora_no_bloquean_max_permitido(create_actor: Any) -> None:
    """Con 2 trámites vencidos (máximo permitido), no se bloquea la presentación."""
    user, actor = create_actor("solic_dos_mora", ["gastos.presentar"])
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra vencida #1",
        fecha_pago=date(2026, 10, 1),
    )
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra vencida #2",
        fecha_pago=date(2026, 10, 5),
    )

    fecha_eval = date(2026, 10, 31)  # 30 y 26 días transcurridos
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)

    assert resumen.total_pendientes == 2
    assert resumen.total_en_mora == 2
    assert resumen.tiene_bloqueo is False  # 2 <= 2

    nueva = crear_solicitud_gasto(
        actor=actor,
        concepto="Solicitud con 2 moras permitidas",
        monto_estimado=Decimal("8000.00"),
        unidad_requirente="Dpto",
        fecha_referencia=fecha_eval,
    )
    assert nueva.pk is not None


def test_tres_tramites_en_mora_bloquean_con_excepcion_especifica(create_actor: Any) -> None:
    """Con 3 trámites vencidos (> 2), crear_solicitud_gasto lanza DeudaDocumentalBloqueoError."""
    user, actor = create_actor("solic_bloqueado", ["gastos.presentar"])
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra vencida #1",
        fecha_pago=date(2026, 10, 1),
    )
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra vencida #2",
        fecha_pago=date(2026, 10, 5),
    )
    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra vencida #3",
        fecha_pago=date(2026, 10, 10),
    )

    fecha_eval = date(2026, 10, 31)  # Todas con > 15 días
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)

    assert resumen.total_pendientes == 3
    assert resumen.total_en_mora == 3
    assert resumen.tiene_bloqueo is True

    with pytest.raises(DeudaDocumentalBloqueoError) as exc_info:
        crear_solicitud_gasto(
            actor=actor,
            concepto="Intento de solicitud bloqueada",
            monto_estimado=Decimal("5000.00"),
            unidad_requirente="Dpto",
            fecha_referencia=fecha_eval,
        )

    err = exc_info.value
    assert "El solicitante registra 3 trámites con rendición de factura" in str(err)
    assert len(err.solicitudes_en_mora) == 3


# ---------------------------------------------------------------------------
# 3. Ciclo de Vida Documental: Aporte, Rechazo y Reemplazo de Factura
# ---------------------------------------------------------------------------


def test_desbloqueo_al_incorporar_factura_proveedor(create_actor: Any) -> None:
    """Al incorporar factura para 1 de las 3 compras, la mora baja a 2 y se desbloquea."""
    user, actor = create_actor("solic_regulariza", ["gastos.presentar", "documentos.incorporar"])
    s1 = _crear_compra_directa_pagada(
        solicitante=user, concepto="Vencida A", fecha_pago=date(2026, 10, 1)
    )
    _crear_compra_directa_pagada(
        solicitante=user, concepto="Vencida B", fecha_pago=date(2026, 10, 5)
    )
    _crear_compra_directa_pagada(
        solicitante=user, concepto="Vencida C", fecha_pago=date(2026, 10, 10)
    )

    fecha_eval = date(2026, 10, 31)
    # Inicialmente bloqueado
    assert verificar_deuda_documental_solicitante(
        actor, fecha_referencia=fecha_eval
    ).tiene_bloqueo is True

    # El solicitante adjunta la factura para la primera compra
    _adjuntar_factura(s1, user)

    # Ahora tiene 2 pendientes en mora (2 <= 2): desbloqueado
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)
    assert resumen.total_en_mora == 2
    assert resumen.tiene_bloqueo is False

    nueva = crear_solicitud_gasto(
        actor=actor,
        concepto="Nueva solicitud tras regularizar 1 factura",
        monto_estimado=Decimal("15000.00"),
        unidad_requirente="Secretaría",
        fecha_referencia=fecha_eval,
    )
    assert nueva.pk is not None


def test_factura_rechazada_no_cancela_deuda_y_mantiene_bloqueo(create_actor: Any) -> None:
    """Si la operadora rechaza la factura aportada, el trámite vuelve a computar como adeudado."""
    user, actor = create_actor("solic_rechazo", ["gastos.presentar", "documentos.incorporar"])
    operadora, _ = create_actor("oper_auditora", ["documentos.revisar"])

    s1 = _crear_compra_directa_pagada(
        solicitante=user, concepto="Compra A", fecha_pago=date(2026, 10, 1)
    )
    _crear_compra_directa_pagada(
        solicitante=user, concepto="Compra B", fecha_pago=date(2026, 10, 5)
    )
    _crear_compra_directa_pagada(
        solicitante=user, concepto="Compra C", fecha_pago=date(2026, 10, 10)
    )

    fecha_eval = date(2026, 10, 31)

    # Solicitante adjunta factura para s1
    factura = _adjuntar_factura(s1, user)
    assert verificar_deuda_documental_solicitante(
        actor, fecha_referencia=fecha_eval
    ).tiene_bloqueo is False

    # Operadora rechaza la factura (ej: CUIT incorrecto o borrosa)
    RevisionDocumento.objects.create(
        documento=factura,
        resultado=RevisionDocumento.Resultado.RECHAZADO,
        motivo="Factura con CUIT incorrecto",
        actor=operadora,
    )

    # Al ser rechazada, s1 vuelve a adeudar factura válida: vuelve a 3 en mora y se bloquea
    resumen_post_rechazo = verificar_deuda_documental_solicitante(
        actor, fecha_referencia=fecha_eval
    )
    assert resumen_post_rechazo.total_en_mora == 3
    assert resumen_post_rechazo.tiene_bloqueo is True

    with pytest.raises(DeudaDocumentalBloqueoError):
        crear_solicitud_gasto(
            actor=actor,
            concepto="Intento fallido tras factura rechazada",
            monto_estimado=Decimal("2000.00"),
            unidad_requirente="Dpto",
            fecha_referencia=fecha_eval,
        )


def test_reemplazo_de_factura_rechazada_desbloquea(create_actor: Any) -> None:
    """Aportar un reemplazo válido de la factura rechazada satisface la deuda y desbloquea."""
    user, actor = create_actor("solic_reemplaza", ["gastos.presentar", "documentos.incorporar"])
    operadora, _ = create_actor("oper_auditora2", ["documentos.revisar"])

    s1 = _crear_compra_directa_pagada(
        solicitante=user, concepto="Compra A", fecha_pago=date(2026, 10, 1)
    )
    _crear_compra_directa_pagada(
        solicitante=user, concepto="Compra B", fecha_pago=date(2026, 10, 5)
    )
    _crear_compra_directa_pagada(
        solicitante=user, concepto="Compra C", fecha_pago=date(2026, 10, 10)
    )

    fecha_eval = date(2026, 10, 31)
    factura_v1 = _adjuntar_factura(s1, user)
    RevisionDocumento.objects.create(
        documento=factura_v1,
        resultado=RevisionDocumento.Resultado.RECHAZADO,
        motivo="Rechazo preliminar",
        actor=operadora,
    )
    assert verificar_deuda_documental_solicitante(
        actor, fecha_referencia=fecha_eval
    ).tiene_bloqueo is True

    # Solicitante reemplaza la factura por una corregida
    factura_v2 = _adjuntar_factura(s1, user, reemplaza=factura_v1)
    assert factura_v2.version == 2

    # La versión vigente (v2) no está rechazada: mora baja a 2 y se desbloquea
    resumen = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_eval)
    assert resumen.total_en_mora == 2
    assert resumen.tiene_bloqueo is False


# ---------------------------------------------------------------------------
# 4. Ergonomía Visual en Vistas (Formulario de Alta y Listado)
# ---------------------------------------------------------------------------


def test_vista_alta_muestra_banner_warning_preventivo_dentro_de_gracia(
    create_actor: Any, auth_client: Any, monkeypatch: Any
) -> None:
    """GET /gastos/presentar/ muestra banner amarillo preventivo si adeuda dentro del plazo."""
    user, _ = create_actor("solic_ui_warning", ["gastos.presentar"])
    client = auth_client(user)

    _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra en plazo de gracia",
        fecha_pago=date(2026, 10, 25),
    )

    # Fijar fecha del sistema simulada
    from django.utils import timezone
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 10, 30))

    response = client.get(reverse("gastos:presentar"))
    assert response.status_code == 200
    html = response.content.decode()

    assert "message-warning" in html
    assert "Aviso preventivo de rendición documental" in html
    assert "Compra en plazo de gracia" in html
    assert "message-error" not in html
    assert 'button type="submit" class="btn">Enviar Solicitud</button>' in html


def test_vista_alta_muestra_banner_error_critico_y_bloquea_boton(
    create_actor: Any, auth_client: Any, monkeypatch: Any
) -> None:
    """GET /gastos/presentar/ muestra banner rojo y bloquea botón al superar 2 moras."""
    user, _ = create_actor("solic_ui_error", ["gastos.presentar"])
    client = auth_client(user)

    for i in range(3):
        _crear_compra_directa_pagada(
            solicitante=user,
            concepto=f"Compra vencida crítica #{i+1}",
            fecha_pago=date(2026, 10, 1),
        )

    from django.utils import timezone
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 10, 31))

    response = client.get(reverse("gastos:presentar"))
    assert response.status_code == 200
    html = response.content.decode()

    assert "message-error" in html
    assert "Bloqueo de nuevas solicitudes por comprobantes adeudados" in html
    assert "Registrás <strong>3</strong> compra(s) directa(s)" in html
    assert "disabled" in html
    assert "Presentación Bloqueada" in html


def test_vista_alta_post_bloqueado_retorna_400(
    create_actor: Any, auth_client: Any, monkeypatch: Any
) -> None:
    """POST /gastos/presentar/ de un solicitante con 3 moras retorna HTTP 400 y no guarda."""
    user, _ = create_actor("solic_post_block", ["gastos.presentar"])
    client = auth_client(user)

    for i in range(3):
        _crear_compra_directa_pagada(
            solicitante=user,
            concepto=f"Mora acumulada #{i+1}",
            fecha_pago=date(2026, 10, 1),
        )

    from django.utils import timezone
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 10, 31))

    conteo_previo = SolicitudGasto.objects.count()
    response = client.post(
        reverse("gastos:presentar"),
        {
            "concepto": "Intento prohibido",
            "monto_estimado": "10000.00",
            "unidad_requirente": "Laboratorio",
            "tipo_flujo": TipoFlujoGasto.COMPRA_DIRECTA,
        },
    )

    assert response.status_code == 400
    html = response.content.decode()
    assert "Presentación bloqueada" in html
    assert "comprobantes pendientes" in html
    assert SolicitudGasto.objects.count() == conteo_previo


def test_vista_listado_muestra_banner_deuda_al_solicitante(
    create_actor: Any, auth_client: Any, monkeypatch: Any
) -> None:
    """GET /gastos/ muestra el banner de aviso de rendición en el panel del solicitante."""
    user, _ = create_actor("solic_list_banner", ["gastos.presentar"])
    client = auth_client(user)

    s_vencida = _crear_compra_directa_pagada(
        solicitante=user,
        concepto="Compra de reactivos químicos",
        fecha_pago=date(2026, 10, 1),
    )

    from django.utils import timezone
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 10, 20))  # 19 días (1 mora)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200
    html = response.content.decode()

    assert "Rendición de comprobantes pendiente" in html
    assert "Compra de reactivos químicos" in html
    assert f'href="/gastos/{s_vencida.pk}/"' in html


def test_aislamiento_deuda_entre_solicitantes(
    create_actor: Any, monkeypatch: Any
) -> None:
    """La deuda documental acumulada por el Solicitante A no bloquea ni afecta al Solicitante B."""
    user_a, actor_a = create_actor("solic_a_deudor", ["gastos.presentar"])
    user_b, actor_b = create_actor("solic_b_limpio", ["gastos.presentar"])

    # Solicitante A acumula 3 moras
    for i in range(3):
        _crear_compra_directa_pagada(
            solicitante=user_a,
            concepto=f"Deuda de A #{i+1}",
            fecha_pago=date(2026, 10, 1),
        )

    fecha_eval = date(2026, 10, 31)

    # Usuario A bloqueado
    assert verificar_deuda_documental_solicitante(
        actor_a, fecha_referencia=fecha_eval
    ).tiene_bloqueo is True

    # Usuario B completamente limpio
    resumen_b = verificar_deuda_documental_solicitante(actor_b, fecha_referencia=fecha_eval)
    assert resumen_b.total_pendientes == 0
    assert resumen_b.tiene_bloqueo is False

    # Usuario B crea solicitud exitosamente
    solicitud_b = crear_solicitud_gasto(
        actor=actor_b,
        concepto="Solicitud independiente de B",
        monto_estimado=Decimal("25000.00"),
        unidad_requirente="Electrónica",
        fecha_referencia=fecha_eval,
    )
    assert solicitud_b.pk is not None
    assert solicitud_b.solicitante_id == user_b.pk
