"""Integración C04 de #49: recorrido HTTP del pago externo con proveedor real
y proyección documental.

Aporta evidencia a los criterios GP-01 a GP-06 de SPEC-011 (la cobertura de GP-06 es parcial):
- Carga y consulta del proveedor real documentos.c01.ProveedorDocumentalGastos.
- Selector de formulario con la referencia documental vigente (GP-02).
- Alta atómica de PagoExterno y EventoPagoExterno con fecha del hecho e importe ARS (GP-03).
- Idempotencia: el reenvío idéntico no duplica pago ni evento (GP-04).
- Conflicto 409 ante reenvío con datos distintos (GP-04).
- Preservación de estado aceptada y monto_estimado sin mutaciones silenciosas (GP-01, GP-05).
- Proyección condicional en el detalle:
  * Factura: categoría factual explícita advirtiendo que revisión desconocida no
    equivale a aprobación documental ni satisface por sí sola el pendiente de factura definitiva.
  * Presupuesto / proforma: explica que falta aportar factura definitiva y que revisión
    desconocida no implica aprobación.
  * Reemplazo documental / degradación neutra: conserva la referencia pagada pero degrada a neutro.
  * No revela UUID ni huella de idempotencia en el detalle.
  * No consulta listado antes del pago o sin metadatos/proveedor disponible (GP-01, GP-05, GP-06).
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento
from documentos.services import incorporar
from gastos.auth import has_capability
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno, SolicitudGasto
from tests.integracion.helpers import archivo_pdf


@pytest.mark.django_db(transaction=True)
def test_c04_pago_real_y_proyeccion_documental(
    escenario_comun, transactional_db, settings, monkeypatch
):
    """Recorrido completo de pago con proveedor real, idempotencia y proyección."""
    # 1. Configurar el proveedor real en settings para la integración
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"

    # Spy/wrapper sobre el método de la clase real ProveedorDocumentalGastos
    # (preservando la implementación real).
    metodo_original_listar = ProveedorDocumentalGastos.listar_opciones_para_pago
    llamadas_listar: list[tuple[Any, ...]] = []

    def spy_listar_opciones_para_pago(self, *args, **kwargs):
        llamadas_listar.append((args, kwargs))
        return metodo_original_listar(self, *args, **kwargs)

    monkeypatch.setattr(
        ProveedorDocumentalGastos,
        "listar_opciones_para_pago",
        spy_listar_opciones_para_pago,
    )

    # Spy/wrapper sobre verificar_y_bloquear_documento delegando al método original
    metodo_original_bloquear = ProveedorDocumentalGastos.verificar_y_bloquear_documento
    llamadas_bloquear: list[tuple[Any, ...]] = []

    def spy_verificar_y_bloquear_documento(self, *args, **kwargs):
        llamadas_bloquear.append((args, kwargs))
        return metodo_original_bloquear(self, *args, **kwargs)

    monkeypatch.setattr(
        ProveedorDocumentalGastos,
        "verificar_y_bloquear_documento",
        spy_verificar_y_bloquear_documento,
    )

    e = escenario_comun
    monto_inicial = e.gasto.monto_estimado
    assert e.gasto.estado == EstadoSolicitud.ACEPTADA

    # Cliente autenticado con capacidades de pago y metadatos (demo_gastos_pago + demo_operadora)
    cliente = Client()
    cliente.force_login(e.staff)

    url_detalle = reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})

    # Verificación previa al pago: demuestra con el spy que el GET de detalle pre-pago
    # no llama listar_opciones_para_pago ni proyecta pago antes de registrarlo
    assert len(llamadas_listar) == 0
    assert len(llamadas_bloquear) == 0
    respuesta_pre_pago = cliente.get(url_detalle)
    assert respuesta_pre_pago.status_code == 200
    assert respuesta_pre_pago.context.get("pago_consulta") is None
    assert respuesta_pre_pago.context.get("respaldo_categoria") is None
    assert len(llamadas_listar) == 0
    assert len(llamadas_bloquear) == 0
    contenido_pre_pago = respuesta_pre_pago.content.decode("utf-8")
    assert "Pago externo registrado" not in contenido_pre_pago
    assert "Respaldo documental registrado" not in contenido_pre_pago

    # 2. Incorporar una factura ficticia al gasto aceptado mediante el servicio real
    documento = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    referencia_version_str = str(documento.referencia_version)

    # 3. GET del formulario de pago: debe listar y mostrar la referencia documental vigente
    url_pagar = reverse("gastos:pagar", kwargs={"pk": e.gasto.pk})
    conteo_listar_antes_get = len(llamadas_listar)
    respuesta_get = cliente.get(url_pagar)
    assert respuesta_get.status_code == 200
    # Aserción positiva: el GET del formulario consulta listar_opciones_para_pago
    assert len(llamadas_listar) == conteo_listar_antes_get + 1
    assert len(llamadas_bloquear) == 0

    contenido_get = respuesta_get.content.decode("utf-8")
    assert referencia_version_str in contenido_get
    opciones = respuesta_get.context.get("opciones_documentales", [])
    assert any(
        op.referencia_documental == referencia_version_str and op.tipo_documento == "factura"
        for op in opciones
    )

    # 4. POST registra pago positivo en ARS con fecha del hecho y referencia externa sintética
    payload = {
        "importe": "1.00",
        "fecha_pago": "2026-10-16",
        "referencia_externa": "SINTETICA-C04-001",
        "referencia_documental": referencia_version_str,
    }
    conteo_bloquear_antes_post = len(llamadas_bloquear)
    respuesta_post = cliente.post(url_pagar, payload)
    assert respuesta_post.status_code == 302
    assert respuesta_post.url == url_detalle
    # Demuestra que el primer POST invoca verificar_y_bloquear_documento una vez
    assert len(llamadas_bloquear) == conteo_bloquear_antes_post + 1

    # 5. Confirmar persistencia atómica de exactamente un PagoExterno y un EventoPagoExterno
    assert PagoExterno.objects.filter(solicitud=e.gasto).count() == 1
    pago = PagoExterno.objects.get(solicitud=e.gasto)
    assert pago.importe == Decimal("1.00")
    assert pago.moneda == "ARS"
    assert pago.fecha_pago == date(2026, 10, 16)
    assert pago.referencia_externa == "SINTETICA-C04-001"
    assert pago.referencia_documental == referencia_version_str

    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1
    evento = EventoPagoExterno.objects.get(pago=pago)
    assert evento.actor_id == e.staff.pk
    assert evento.tipo_evento == "pago_externo_registrado"

    # 6. Reenviar el POST idéntico no duplica pago ni evento (idempotencia estricta)
    conteo_bloquear_antes_reenvio = len(llamadas_bloquear)
    conteo_listar_antes_reenvio = len(llamadas_listar)
    respuesta_reenvio = cliente.post(url_pagar, payload)
    assert respuesta_reenvio.status_code == 302
    assert respuesta_reenvio.url == url_detalle

    assert PagoExterno.objects.filter(solicitud=e.gasto).count() == 1
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1
    # Demuestra que el reenvío idéntico no vuelve a invocar verificar_y_bloquear_documento ni listar
    assert len(llamadas_bloquear) == conteo_bloquear_antes_reenvio
    assert len(llamadas_listar) == conteo_listar_antes_reenvio

    # 7. Reenvío con payload conflictivo (importe distinto) produce 409 sin modificar registros
    payload_conflicto = {**payload, "importe": "2.00"}
    conteo_bloquear_antes_conflicto = len(llamadas_bloquear)
    conteo_listar_antes_conflicto = len(llamadas_listar)
    respuesta_conflicto = cliente.post(url_pagar, payload_conflicto)
    assert respuesta_conflicto.status_code == 409
    assert PagoExterno.objects.filter(solicitud=e.gasto).count() == 1
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1
    # Demuestra que el reenvío conflictivo tampoco vuelve a llamar a verificar ni a listar
    assert len(llamadas_bloquear) == conteo_bloquear_antes_conflicto
    assert len(llamadas_listar) == conteo_listar_antes_conflicto

    # 8. El gasto conserva estado aceptada y monto_estimado inalterado
    e.gasto.refresh_from_db()
    assert e.gasto.estado == EstadoSolicitud.ACEPTADA
    assert e.gasto.monto_estimado == Decimal(str(monto_inicial))

    # 9. GET detalle proyecta el pago informativo y la categoría factual 'factura'
    conteo_listar_antes_detalle = len(llamadas_listar)
    respuesta_detalle = cliente.get(url_detalle)
    assert respuesta_detalle.status_code == 200
    # Aserción positiva: sí se consulta listar_opciones_para_pago en el detalle pagado
    # mientras el permiso y el proveedor existen
    assert len(llamadas_listar) == conteo_listar_antes_detalle + 1
    pago_consulta = respuesta_detalle.context.get("pago_consulta")
    assert pago_consulta is not None
    # Aserción explícita de que pago_consulta carece de referencia_documental
    assert not hasattr(pago_consulta, "referencia_documental")
    assert respuesta_detalle.context.get("respaldo_categoria") == "factura"

    contenido_detalle = respuesta_detalle.content.decode("utf-8")
    # Proyección informativa del pago
    assert "Pago externo registrado" in contenido_detalle
    assert "1,00" in contenido_detalle or "1.00" in contenido_detalle
    assert "ARS" in contenido_detalle
    assert "SINTETICA-C04-001" in contenido_detalle
    assert "16/10/2026" in contenido_detalle
    assert "Registro informativo de la demo" in contenido_detalle

    # Texto condicional para categoría factura: expresa límites de revisión y factura definitiva
    assert "Respaldo documental registrado: factura." in contenido_detalle
    assert (
        "Un estado de revisión desconocido no equivale a aprobación documental "
        "ni satisface por sí sola el pendiente de factura definitiva."
        in contenido_detalle
    )
    assert "presupuesto/proforma" not in contenido_detalle

    # Garantía de privacidad: detalle no revela UUID de versión, serie ni huella de idempotencia
    assert referencia_version_str not in contenido_detalle
    assert str(documento.serie) not in contenido_detalle
    assert pago.huella_idempotencia not in contenido_detalle

    # 10. Reemplazo documental: conserva la referencia pagada pero degrada proyección a neutro
    doc_reemplazo = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
        reemplaza_id=documento.pk,
    )
    pago.refresh_from_db()
    # La referencia pagada en PagoExterno se conserva inmutable
    assert pago.referencia_documental == referencia_version_str
    assert pago.referencia_documental != str(doc_reemplazo.referencia_version)

    # Detalle con versión reemplazada degrada a categoría None con texto neutro
    conteo_listar_antes_reemplazo = len(llamadas_listar)
    respuesta_reemplazo = cliente.get(url_detalle)
    assert respuesta_reemplazo.status_code == 200
    # Aserción positiva: la consulta posterior a la versión reemplazada causa un listado actual
    # ante el proveedor, pero la proyección del pago se degrada a neutro (respaldo_categoria=None)
    assert len(llamadas_listar) == conteo_listar_antes_reemplazo + 1
    pago_consulta_reemplazo = respuesta_reemplazo.context.get("pago_consulta")
    assert pago_consulta_reemplazo is not None
    # Aserción explícita de que pago_consulta carece de referencia_documental
    assert not hasattr(pago_consulta_reemplazo, "referencia_documental")
    assert respuesta_reemplazo.context.get("respaldo_categoria") is None
    contenido_reemplazo = respuesta_reemplazo.content.decode("utf-8")
    assert (
        "Esta vista no muestra metadatos ni estado de revisión del comprobante. "
        "El registro de pago no equivale a aprobación documental "
        "ni acredita la factura definitiva pendiente."
        in contenido_reemplazo
    )
    assert "Respaldo documental registrado: factura." not in contenido_reemplazo
    # Ni la versión v1 pagada ni la v2 aparecen en el detalle post-reemplazo
    assert referencia_version_str not in contenido_reemplazo
    assert str(doc_reemplazo.referencia_version) not in contenido_reemplazo

    # 11. Escenario con presupuesto/proforma: comprueba texto distinto
    # escenario_comun inserta un gasto con pk fija y no avanza la secuencia de PostgreSQL.
    gasto_presupuesto = SolicitudGasto.objects.create(
        pk=e.gasto.pk + 100000,
        concepto="Gasto con presupuesto ficticio",
        monto_estimado=Decimal("50.00"),
        unidad_requirente="Unidad presupuesto",
        solicitante=e.a,
        estado=EstadoSolicitud.ACEPTADA,
    )
    doc_presupuesto = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{gasto_presupuesto.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia="SOLICITANTE",
    )
    ref_presupuesto_str = str(doc_presupuesto.referencia_version)
    url_pagar_presupuesto = reverse("gastos:pagar", kwargs={"pk": gasto_presupuesto.pk})
    payload_presupuesto = {
        "importe": "50.00",
        "fecha_pago": "2026-10-16",
        "referencia_externa": "SINTETICA-C04-PRES",
        "referencia_documental": ref_presupuesto_str,
    }
    resp_post_presupuesto = cliente.post(url_pagar_presupuesto, payload_presupuesto)
    assert resp_post_presupuesto.status_code == 302
    url_detalle_presupuesto = reverse("gastos:detalle", kwargs={"pk": gasto_presupuesto.pk})
    assert resp_post_presupuesto.url == url_detalle_presupuesto

    conteo_listar_antes_presupuesto = len(llamadas_listar)
    respuesta_detalle_presupuesto = cliente.get(url_detalle_presupuesto)
    assert respuesta_detalle_presupuesto.status_code == 200
    # Aserción positiva: sí se consulta listar_opciones_para_pago en el detalle con presupuesto
    assert len(llamadas_listar) == conteo_listar_antes_presupuesto + 1
    pago_consulta_presupuesto = respuesta_detalle_presupuesto.context.get("pago_consulta")
    assert pago_consulta_presupuesto is not None
    assert not hasattr(pago_consulta_presupuesto, "referencia_documental")
    assert respuesta_detalle_presupuesto.context.get("respaldo_categoria") == "presupuesto"
    contenido_presupuesto = respuesta_detalle_presupuesto.content.decode("utf-8")

    # Texto condicional para categoría presupuesto: explica falta de factura definitiva
    assert "Respaldo documental registrado: presupuesto/proforma." in contenido_presupuesto
    assert (
        "Falta aportar factura definitiva y un estado de revisión desconocido "
        "no implica aprobación documental."
        in contenido_presupuesto
    )
    assert "Respaldo documental registrado: factura." not in contenido_presupuesto
    assert ref_presupuesto_str not in contenido_presupuesto

    # 12. Sin metadatos o sin proveedor: no consulta listado y degrada a neutro (status 200)
    # 12.a Actor con solo 'gastos.consultar_todas' y sin 'documentos.ver_metadatos'
    # (grupo demo_lectura)
    grupo_lectura, _ = Group.objects.get_or_create(name="demo_lectura")
    user_lector = get_user_model().objects.create_user(
        username="lector_sin_metadatos", password="demo"
    )
    user_lector.groups.add(grupo_lectura)
    cliente_lector = Client()
    cliente_lector.force_login(user_lector)

    conteo_antes_lector = len(llamadas_listar)
    respuesta_lector = cliente_lector.get(url_detalle_presupuesto)
    assert respuesta_lector.status_code == 200

    # Asegúrate de que el grupo demo_lectura realmente consulta el gasto
    actor_lector = respuesta_lector.context.get("actor")
    assert actor_lector is not None
    assert has_capability(actor_lector, "gastos.consultar_todas")
    # Explica el propósito del escenario: el actor carece de 'documentos.ver_metadatos'
    assert not has_capability(actor_lector, "documentos.ver_metadatos")
    assert not has_capability(actor_lector, "gastos.registrar_pago")
    assert respuesta_lector.context.get("solicitud") == gasto_presupuesto
    assert respuesta_lector.context.get("solicitud").concepto == gasto_presupuesto.concepto
    pago_consulta_lector = respuesta_lector.context.get("pago_consulta")
    assert pago_consulta_lector is not None
    assert pago_consulta_lector.solicitud_id == gasto_presupuesto.pk
    # Aserción explícita de que pago_consulta carece de referencia_documental
    assert not hasattr(pago_consulta_lector, "referencia_documental")
    assert respuesta_lector.context.get("respaldo_categoria") is None

    # Demuestra con el spy que NO se llama a listar_opciones_para_pago para un actor
    # con solo gastos.consultar_todas y sin documentos.ver_metadatos
    assert len(llamadas_listar) == conteo_antes_lector

    contenido_lector = respuesta_lector.content.decode("utf-8")
    assert gasto_presupuesto.concepto in contenido_lector
    assert "Pago externo registrado" in contenido_lector
    assert "SINTETICA-C04-PRES" in contenido_lector
    assert (
        "Esta vista no muestra metadatos ni estado de revisión del comprobante. "
        "El registro de pago no equivale a aprobación documental "
        "ni acredita la factura definitiva pendiente."
        in contenido_lector
    )
    assert "Respaldo documental registrado: presupuesto/proforma." not in contenido_lector
    assert ref_presupuesto_str not in contenido_lector

    # 12.b Proveedor documental desconfigurado en el servidor
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None
    conteo_antes_sin_prov = len(llamadas_listar)
    respuesta_sin_proveedor = cliente.get(url_detalle_presupuesto)
    assert respuesta_sin_proveedor.status_code == 200
    pago_consulta_sin_prov = respuesta_sin_proveedor.context.get("pago_consulta")
    assert pago_consulta_sin_prov is not None
    assert not hasattr(pago_consulta_sin_prov, "referencia_documental")
    assert respuesta_sin_proveedor.context.get("respaldo_categoria") is None

    # Verifica con el spy que no se llama a listar_opciones_para_pago con proveedor no configurado
    assert len(llamadas_listar) == conteo_antes_sin_prov

    contenido_sin_proveedor = respuesta_sin_proveedor.content.decode("utf-8")
    assert (
        "Esta vista no muestra metadatos ni estado de revisión del comprobante. "
        "El registro de pago no equivale a aprobación documental "
        "ni acredita la factura definitiva pendiente."
        in contenido_sin_proveedor
    )
