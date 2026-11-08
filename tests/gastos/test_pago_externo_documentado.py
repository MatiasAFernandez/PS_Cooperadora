"""Comportamiento del registro de pago documentado (PDF bancario + ATP + rectificación).

Cubre la regla nueva: PDF bancario obligatorio, neto derivado en servidor,
constancia ATP posterior, rectificación con versión esperada e historial
append-only, reenvíos contra el alta original, compensación de archivos,
permisos por acción/objeto, datos legados y reflejo en reportes.
"""

from datetime import date
from decimal import Decimal
from threading import Barrier, Thread

import pytest
from django.db import IntegrityError, connections
from django.urls import reverse

from documentos.models import Documento
from gastos.models import (
    EventoPagoExterno,
    PagoExterno,
    PagoExternoCambio,
    PagoExternoOriginal,
)
from gastos.payments import (
    PaymentConflictError,
    PaymentDocumentRequiredError,
    PaymentExpenseNotFoundError,
    PaymentInvalidInputError,
    PaymentPermissionDeniedError,
    PaymentVersionConflictError,
    consultar_pago_externo,
    incorporar_constancia_atp_posterior,
    rectificar_pago_externo,
    registrar_pago_externo,
)
from gastos.reports import obtener_reporte_cuatrimestral_gastos
from identidad.services import Actor
from tests.soporte_pagos import (
    jpg_comprobante,
    pdf_comprobante,
    pdf_constancia,
    pdf_falso,
    png_comprobante,
    webp_invalido,
)

pytestmark = pytest.mark.django_db(transaction=True)

CAPS_PAGO = (
    "gastos.registrar_pago",
    "gastos.consultar_todas",
    "documentos.incorporar",
    "documentos.ver_metadatos",
)


def _payload(**overrides):
    base = {
        "monto_bruto": Decimal("1000.00"),
        "monto_retencion_atp": Decimal("0.00"),
        "fecha_pago": date(2026, 3, 10),
        "referencia_externa": "TRF-DOC-1",
        "referencia_documental": "doc-version-1",
        "comprobante_bancario": pdf_comprobante(),
    }
    base.update(overrides)
    return base


def _registrar(actor, solicitud, provider, **overrides):
    return registrar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        document_provider=provider,
        **_payload(**overrides),
    )


def _sin_archivos(raiz) -> bool:
    return not raiz.exists() or not any(ruta.is_file() for ruta in raiz.rglob("*"))


def _archivos(raiz) -> set:
    return {ruta for ruta in raiz.rglob("*") if ruta.is_file()}


# --------------------------------------------------------------------------- #
# Comprobante obligatorio y validación PDF
# --------------------------------------------------------------------------- #


def test_alta_sin_pdf_bancario_no_escribe_pago_documento_ni_evento(
    actor_factory, solicitud_factory, fake_document_provider, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with pytest.raises(PaymentDocumentRequiredError):
        registrar_pago_externo(
            actor=actor,
            solicitud_id=solicitud.pk,
            document_provider=fake_document_provider(),
            **_payload(comprobante_bancario=None),
        )

    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0
    assert PagoExternoOriginal.objects.count() == 0
    assert Documento.objects.count() == 0
    assert _sin_archivos(settings.DOCUMENT_STORAGE_ROOT)


def test_alta_con_archivo_falso_no_escribe_ni_crea_documento(
    actor_factory, solicitud_factory, fake_document_provider, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with pytest.raises(PaymentInvalidInputError):
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            comprobante_bancario=pdf_falso(),
        )

    assert PagoExterno.objects.count() == 0
    assert Documento.objects.count() == 0
    assert _sin_archivos(settings.DOCUMENT_STORAGE_ROOT)


def test_neto_se_deriva_de_bruto_menos_retencion_y_no_acepta_neto_incoherente(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with pytest.raises(PaymentInvalidInputError):
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("100.00"),
            importe=Decimal("950.00"),
        )

    pago = _registrar(
        actor,
        solicitud,
        fake_document_provider(),
        monto_bruto=Decimal("1000.00"),
        monto_retencion_atp=Decimal("100.00"),
        incorporar_atp_despues=True,
    )
    assert pago.importe == Decimal("900.00")
    assert pago.monto_bruto == Decimal("1000.00")
    assert pago.monto_retencion_atp == Decimal("100.00")


# --------------------------------------------------------------------------- #
# Compensación de archivos y SQL
# --------------------------------------------------------------------------- #


def test_fallo_del_segundo_archivo_compensa_el_primero(
    actor_factory, solicitud_factory, fake_document_provider, monkeypatch, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    from documentos.services import incorporar as incorporar_real

    llamadas: list[str] = []

    def incorporar_falla_segundo(**kwargs):
        llamadas.append(kwargs["tipo"])
        if len(llamadas) == 2:
            raise OSError("fallo sintético del segundo archivo")
        return incorporar_real(**kwargs)

    monkeypatch.setattr(
        "documentos.services.incorporar", incorporar_falla_segundo
    )

    with pytest.raises(OSError):
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("100.00"),
            constancia_atp=pdf_constancia(),
        )

    assert llamadas == ["COMPROBANTE_PAGO", "CONSTANCIA_RETENCION_ATP"]
    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0
    assert Documento.objects.count() == 0
    assert _sin_archivos(settings.DOCUMENT_STORAGE_ROOT)


def test_fallo_sql_despues_de_dos_documentos_compensa_archivos_y_filas(
    actor_factory, solicitud_factory, fake_document_provider, monkeypatch, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    def falla_sql(**kwargs):
        raise RuntimeError("fallo sintético al crear el pago")

    monkeypatch.setattr("gastos.payments.PagoExterno.objects.create", falla_sql)

    with pytest.raises(RuntimeError):
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("100.00"),
            constancia_atp=pdf_constancia(),
        )

    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0
    assert Documento.objects.count() == 0
    assert _sin_archivos(settings.DOCUMENT_STORAGE_ROOT)


def test_reemplazo_de_pdf_con_fallo_sql_compensa_el_archivo_nuevo(
    actor_factory, solicitud_factory, fake_document_provider, monkeypatch, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())
    documento_original_id = pago.comprobante_bancario_id
    archivos_iniciales = _archivos(settings.DOCUMENT_STORAGE_ROOT)

    def falla_sql(**kwargs):
        raise RuntimeError("fallo sintético al registrar la rectificación")

    monkeypatch.setattr("gastos.payments.PagoExternoCambio.objects.create", falla_sql)

    with pytest.raises(RuntimeError):
        rectificar_pago_externo(
            actor=actor,
            solicitud_id=solicitud.pk,
            version_esperada=pago.version,
            motivo="Reemplazo de comprobante con fallo sintético.",
            fecha_pago=date(2026, 3, 11),
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("0.00"),
            referencia_externa="TRF-DOC-1",
            comprobante_bancario=pdf_comprobante("reemplazo.pdf"),
        )

    pago.refresh_from_db()
    assert pago.version == 1
    assert pago.comprobante_bancario_id == documento_original_id
    assert Documento.objects.count() == 1
    assert PagoExternoCambio.objects.count() == 0
    assert _archivos(settings.DOCUMENT_STORAGE_ROOT) == archivos_iniciales


def test_incorporacion_atp_con_fallo_sql_compensa_el_archivo(
    actor_factory, solicitud_factory, fake_document_provider, monkeypatch, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(
        actor,
        solicitud,
        fake_document_provider(),
        monto_bruto=Decimal("100000.00"),
        monto_retencion_atp=Decimal("3500.00"),
        incorporar_atp_despues=True,
    )
    archivos_iniciales = _archivos(settings.DOCUMENT_STORAGE_ROOT)

    def falla_sql(**kwargs):
        raise RuntimeError("fallo sintético al vincular la constancia ATP")

    monkeypatch.setattr("gastos.payments.PagoExternoCambio.objects.create", falla_sql)

    with pytest.raises(RuntimeError):
        incorporar_constancia_atp_posterior(
            actor=actor,
            solicitud_id=solicitud.pk,
            version_esperada=pago.version,
            motivo="Constancia ATP con fallo sintético.",
            constancia_atp=pdf_constancia(),
        )

    pago.refresh_from_db()
    assert pago.version == 1
    assert pago.constancia_atp_id is None
    assert not Documento.objects.filter(
        tipo=Documento.Tipo.CONSTANCIA_RETENCION_ATP
    ).exists()
    assert PagoExternoCambio.objects.count() == 0
    assert _archivos(settings.DOCUMENT_STORAGE_ROOT) == archivos_iniciales


# --------------------------------------------------------------------------- #
# Reenvíos originales y rectificación
# --------------------------------------------------------------------------- #


def test_reenvio_identico_despues_de_rectificar_no_revierte_ni_duplica(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())

    rectificado = rectificar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        motivo="Corrección de importe informada por el banco.",
        fecha_pago=date(2026, 3, 11),
        monto_bruto=Decimal("900.00"),
        monto_retencion_atp=Decimal("0.00"),
        referencia_externa="TRF-DOC-1",
    )
    assert rectificado.version == 2
    assert rectificado.importe == Decimal("900.00")

    # El reenvío del alta original no revierte la rectificación ni crea otro pago.
    reenvio = _registrar(actor, solicitud, fake_document_provider())
    assert reenvio.pk == pago.pk
    reenvio.refresh_from_db()
    assert reenvio.version == 2
    assert reenvio.importe == Decimal("900.00")
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExternoCambio.objects.count() == 1
    assert Documento.objects.filter(tipo=Documento.Tipo.COMPROBANTE_PAGO).count() == 1


def test_rectificacion_reconoce_reenvio_exacto_sin_nuevo_cambio(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())

    kwargs = {
        "actor": actor,
        "solicitud_id": solicitud.pk,
        "version_esperada": pago.version,
        "motivo": "Corrección de fecha.",
        "fecha_pago": date(2026, 3, 12),
        "monto_bruto": Decimal("1000.00"),
        "monto_retencion_atp": Decimal("0.00"),
        "referencia_externa": "TRF-DOC-1",
    }
    primero = rectificar_pago_externo(**kwargs)
    segundo = rectificar_pago_externo(**kwargs)

    assert segundo.pk == primero.pk
    assert segundo.version == 2
    assert PagoExternoCambio.objects.count() == 1
    assert Documento.objects.count() == 1


def test_historial_de_cambio_es_append_only(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())
    rectificar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        motivo="Corrección append-only.",
        fecha_pago=date(2026, 3, 11),
        monto_bruto=Decimal("900.00"),
        monto_retencion_atp=Decimal("0.00"),
    )
    cambio = PagoExternoCambio.objects.get()
    cambio.motivo = "Intento de reescritura"
    with pytest.raises(IntegrityError):
        cambio.save()
    with pytest.raises(IntegrityError):
        PagoExternoCambio.objects.filter(pk=cambio.pk).update(motivo="x")
    with pytest.raises(IntegrityError):
        cambio.delete()
    assert PagoExternoCambio.objects.get().motivo == "Corrección append-only."


def test_rectificacion_concurrente_una_version_gana_y_la_otra_conflicta(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())
    version_inicial = pago.version
    barrera = Barrier(2)
    resultados: list = [None, None]
    importes = (Decimal("900.00"), Decimal("800.00"))

    def worker(indice: int) -> None:
        connections.close_all()
        try:
            barrera.wait(timeout=10)
            resultados[indice] = rectificar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                version_esperada=version_inicial,
                motivo=f"Corrección concurrente {indice}",
                fecha_pago=date(2026, 3, 11),
                monto_bruto=importes[indice],
                monto_retencion_atp=Decimal("0.00"),
                referencia_externa="TRF-DOC-1",
            )
        except Exception as exc:  # noqa: BLE001 - se evalúa el resultado del hilo
            resultados[indice] = exc
        finally:
            connections.close_all()

    hilos = [Thread(target=worker, args=(indice,)) for indice in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=25)
    for hilo in hilos:
        assert not hilo.is_alive()

    exitos = [r for r in resultados if isinstance(r, PagoExterno)]
    conflictos = [r for r in resultados if isinstance(r, PaymentVersionConflictError)]
    assert len(exitos) == 1, resultados
    assert len(conflictos) == 1, resultados
    pago.refresh_from_db()
    assert pago.version == 2
    assert PagoExternoCambio.objects.count() == 1
    assert pago.importe in importes


# --------------------------------------------------------------------------- #
# ATP posterior
# --------------------------------------------------------------------------- #


def test_atp_posterior_deja_pendiente_visible_y_reenvio_no_duplica(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(
        actor,
        solicitud,
        fake_document_provider(),
        monto_bruto=Decimal("100000.00"),
        monto_retencion_atp=Decimal("3500.00"),
        incorporar_atp_despues=True,
    )
    assert pago.constancia_atp is None
    assert pago.constancia_atp_pendiente is True
    consulta = consultar_pago_externo(actor, solicitud.pk)
    assert consulta is not None and consulta.constancia_atp_pendiente is True

    kwargs = {
        "actor": actor,
        "solicitud_id": solicitud.pk,
        "version_esperada": pago.version,
        "motivo": "Constancia aportada por la operadora.",
        "constancia_atp": pdf_constancia(),
    }
    actualizado = incorporar_constancia_atp_posterior(**kwargs)
    assert actualizado.version == 2
    assert actualizado.constancia_atp is not None
    assert actualizado.constancia_atp.tipo == Documento.Tipo.CONSTANCIA_RETENCION_ATP
    assert actualizado.constancia_atp_pendiente is False

    reenvio = incorporar_constancia_atp_posterior(
        **{**kwargs, "constancia_atp": pdf_constancia()}
    )
    assert reenvio.pk == actualizado.pk
    assert reenvio.version == 2
    assert Documento.objects.filter(tipo=Documento.Tipo.CONSTANCIA_RETENCION_ATP).count() == 1
    assert PagoExternoCambio.objects.count() == 1

    with pytest.raises(PaymentConflictError):
        incorporar_constancia_atp_posterior(
            **{
                **kwargs,
                "motivo": "Otro motivo distinto.",
                "constancia_atp": pdf_constancia(),
            }
        )


# --------------------------------------------------------------------------- #
# Permisos, objeto y descarga
# --------------------------------------------------------------------------- #


def test_rectificar_datos_solo_exige_pago_y_visibilidad(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())
    _, actor_sin_pago = actor_factory(("gastos.consultar_todas",))
    with pytest.raises(PaymentPermissionDeniedError):
        rectificar_pago_externo(
            actor=actor_sin_pago,
            solicitud_id=solicitud.pk,
            version_esperada=pago.version,
            motivo="Sin permiso",
            fecha_pago=date(2026, 3, 11),
            monto_bruto=Decimal("900.00"),
        )
    _, actor_solo_pago = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    rectificado = rectificar_pago_externo(
        actor=actor_solo_pago,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        motivo="Corrección de datos sin tocar documentos.",
        fecha_pago=date(2026, 3, 12),
        monto_bruto=Decimal("900.00"),
        monto_retencion_atp=Decimal("0.00"),
        referencia_externa="TRF-DOC-1",
    )
    assert rectificado.version == 2
    assert rectificado.comprobante_bancario_id == pago.comprobante_bancario_id

    _, actor_ajeno = actor_factory(("gastos.registrar_pago", "gastos.consultar_propias"))
    with pytest.raises(PaymentExpenseNotFoundError):
        rectificar_pago_externo(
            actor=actor_ajeno,
            solicitud_id=solicitud.pk,
            version_esperada=rectificado.version,
            motivo="Sin visibilidad",
            fecha_pago=date(2026, 3, 11),
            monto_bruto=Decimal("900.00"),
        )


def test_reemplazo_de_pdf_exige_capacidades_documentales(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())
    _, actor_sin_docs = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )

    with pytest.raises(PaymentPermissionDeniedError):
        rectificar_pago_externo(
            actor=actor_sin_docs,
            solicitud_id=solicitud.pk,
            version_esperada=pago.version,
            motivo="Reemplazo sin permiso documental",
            fecha_pago=date(2026, 3, 11),
            monto_bruto=Decimal("1000.00"),
            comprobante_bancario=pdf_comprobante("nuevo.pdf"),
        )
    assert Documento.objects.filter(tipo=Documento.Tipo.COMPROBANTE_PAGO).count() == 1


def test_descarga_posterior_autoriza_por_endpoint(
    actor_factory, solicitud_factory, fake_document_provider, monkeypatch, auth_client
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())
    documento = pago.comprobante_bancario
    assert documento is not None
    url = reverse("documentos:archivo", args=[documento.pk])

    lector = Actor(
        subject_id=user.pk,
        capabilities=frozenset(("gastos.consultar_todas", "documentos.consultar_metadatos")),
    )
    monkeypatch.setattr("documentos.views.resolve_actor", lambda request: lector)
    assert auth_client(user, lector).get(url).status_code == 403

    descargador = Actor(
        subject_id=user.pk,
        capabilities=frozenset(
            (
                "gastos.consultar_todas",
                "documentos.consultar_metadatos",
                "documentos.recuperar_contenido",
            )
        ),
    )
    monkeypatch.setattr("documentos.views.resolve_actor", lambda request: descargador)
    response = auth_client(user, descargador).get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"%PDF-")


# --------------------------------------------------------------------------- #
# Datos legados y reportes
# --------------------------------------------------------------------------- #


def test_pago_legado_sin_pdf_se_preserva_y_no_se_le_fabrica_comprobante(
    actor_factory, solicitud_factory, auth_client, monkeypatch
) -> None:
    user, actor = actor_factory(("gastos.registrar_pago", "gastos.consultar_todas"))
    solicitud = solicitud_factory(solicitante=user)
    pago = PagoExterno.objects.create(
        solicitud=solicitud,
        importe=Decimal("825.40"),
        monto_bruto=Decimal("825.40"),
        monto_retencion_atp=Decimal("0.00"),
        moneda="ARS",
        fecha_pago=date(2026, 3, 10),
        referencia_externa="LEGADO-1",
        referencia_documental="doc-legado",
        huella_idempotencia="a" * 64,
    )
    consulta = consultar_pago_externo(actor, solicitud.pk)
    assert consulta is not None
    assert consulta.es_registro_legado is True
    assert consulta.tiene_comprobante_bancario is False
    assert Documento.objects.count() == 0

    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    contenido = auth_client(user, actor).get(
        reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    ).content.decode()
    assert "Registro histórico sin comprobante" in contenido

    reenvio = registrar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        document_provider=None,
        **_payload(
            monto_bruto=Decimal("825.40"),
            fecha_pago=date(2026, 3, 10),
            referencia_externa="LEGADO-1",
            referencia_documental="doc-legado",
            comprobante_bancario=None,
        ),
    )
    assert reenvio.pk == pago.pk
    assert Documento.objects.count() == 0


def test_reporte_refleja_la_fila_efectiva_sin_sumar_eventos_como_pagos(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(
        actor,
        solicitud,
        fake_document_provider(),
        monto_bruto=Decimal("1000.00"),
        fecha_pago=date(2026, 3, 10),
    )
    rectificar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        motivo="Corrección de fecha e importe.",
        fecha_pago=date(2026, 7, 15),
        monto_bruto=Decimal("1200.00"),
        monto_retencion_atp=Decimal("0.00"),
        referencia_externa="TRF-DOC-1",
    )

    reporte = obtener_reporte_cuatrimestral_gastos(2026)
    c1, c2, _ = reporte.cuatrimestres
    assert c1.cantidad_pagos == 0
    assert c2.cantidad_pagos == 1
    assert c2.monto_erogado_bruto == Decimal("1200.00")
    assert c2.monto_neto_transferido == Decimal("1200.00")
    assert reporte.totales.cantidad_pagos == 1
    assert reporte.totales.monto_erogado_bruto == Decimal("1200.00")


# --------------------------------------------------------------------------- #
# Pantalla: readonly, sin alícuota automática y datos conservados
# --------------------------------------------------------------------------- #


def test_formulario_muestra_neto_readonly_y_no_infiere_alicuota(
    actor_factory, solicitud_factory, auth_client, monkeypatch, settings, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud = solicitud_factory(solicitante=user)
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(
        opciones=[]
    )
    response = auth_client(user, actor).get(
        reverse("gastos:pagar", kwargs={"pk": solicitud.pk})
    )
    assert response.status_code == 200
    contenido = response.content.decode()
    assert 'id="rp-neto"' in contenido
    assert "readonly" in contenido
    assert "Calculado" in contenido
    assert "data-base-imponible" in contenido
    assert "3,50%" not in contenido
    assert "3.50%" not in contenido
    assert 'name="importe"' not in contenido


def test_alta_comprobante_imagen_jpg_y_png_escribe_documento_y_pago(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud1 = solicitud_factory(solicitante=user)
    pago1 = _registrar(
        actor,
        solicitud1,
        fake_document_provider(),
        comprobante_bancario=jpg_comprobante("recibo.jpg"),
    )
    assert pago1.comprobante_bancario.formato == "image/jpeg"
    assert pago1.comprobante_bancario.nombre_original == "recibo.jpg"

    solicitud2 = solicitud_factory(solicitante=user)
    pago2 = _registrar(
        actor,
        solicitud2,
        fake_document_provider(),
        comprobante_bancario=png_comprobante("recibo.png"),
    )
    assert pago2.comprobante_bancario.formato == "image/png"
    assert pago2.comprobante_bancario.nombre_original == "recibo.png"


def test_alta_comprobante_formato_no_permitido_webp_rechaza(
    actor_factory, solicitud_factory, fake_document_provider, settings
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with pytest.raises(PaymentInvalidInputError) as exc_info:
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            comprobante_bancario=webp_invalido(),
        )
    assert "El comprobante bancario" in str(exc_info.value)
    assert PagoExterno.objects.count() == 0
    assert Documento.objects.count() == 0
    assert _sin_archivos(settings.DOCUMENT_STORAGE_ROOT)


def test_alta_diferir_atp_con_archivo_o_referencia_incoherente_rechaza(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    # Diferir ATP pero enviando archivo de constancia
    with pytest.raises(PaymentInvalidInputError) as exc_file:
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("150000.00"),
            monto_retencion_atp=Decimal("5250.00"),
            incorporar_atp_despues=True,
            constancia_atp=pdf_constancia(),
        )
    assert "Al diferir la constancia ATP no se debe adjuntar un archivo" in str(exc_file.value)

    # Diferir ATP pero enviando referencia
    with pytest.raises(PaymentInvalidInputError) as exc_ref:
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("150000.00"),
            monto_retencion_atp=Decimal("5250.00"),
            incorporar_atp_despues=True,
            referencia_atp="REF-ATP-INCOHERENTE",
        )
    assert "Al diferir la constancia ATP no se debe informar una referencia" in str(exc_ref.value)


def test_constancia_atp_conserva_regla_estricta_pdf(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with pytest.raises(PaymentInvalidInputError) as exc_info:
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("150000.00"),
            monto_retencion_atp=Decimal("5250.00"),
            incorporar_atp_despues=False,
            constancia_atp=jpg_comprobante("constancia.jpg"),
        )
    assert "La constancia ATP debe ser un archivo PDF" in str(exc_info.value)


def test_retencion_mayor_o_igual_al_bruto_rechaza(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    # Retención igual al bruto
    with pytest.raises(PaymentInvalidInputError) as exc_igual:
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("1000.00"),
        )
    assert "La retención debe ser menor que el monto bruto" in str(exc_igual.value)

    # Retención mayor al bruto
    with pytest.raises(PaymentInvalidInputError) as exc_mayor:
        _registrar(
            actor,
            solicitud,
            fake_document_provider(),
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("1200.00"),
        )
    assert "La retención debe ser menor que el monto bruto" in str(exc_mayor.value)


def test_normalizacion_importes_formato_es_ar(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    pago = _registrar(
        actor,
        solicitud,
        fake_document_provider(),
        monto_bruto="150.000,00",
        monto_retencion_atp="5.250,00",
        constancia_atp=pdf_constancia(),
    )
    assert pago.monto_bruto == Decimal("150000.00")
    assert pago.monto_retencion_atp == Decimal("5250.00")
    assert pago.importe == Decimal("144750.00")


def test_rectificacion_admite_reemplazo_con_imagen(
    actor_factory, solicitud_factory, fake_document_provider
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    pago = _registrar(actor, solicitud, fake_document_provider())

    rectificado = rectificar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        motivo="Reemplazo con captura JPG",
        fecha_pago=pago.fecha_pago,
        monto_bruto=pago.monto_bruto,
        monto_retencion_atp=pago.monto_retencion_atp,
        comprobante_bancario=jpg_comprobante("captura_transferencia.jpg"),
    )
    assert rectificado.version == 2
    assert rectificado.comprobante_bancario.formato == "image/jpeg"
