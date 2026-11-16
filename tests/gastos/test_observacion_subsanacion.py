"""Pruebas focalizadas para observación y subsanación de solicitudes de gasto (#134)."""

from decimal import Decimal
from threading import Barrier, Thread
from typing import Any

import pytest
from django.core import mail
from django.db import IntegrityError, connections
from django.test import Client
from django.urls import reverse

from avisos.models import Aviso, IntencionCorreo, TipoAviso
from avisos.services import generar_aviso_decision_gasto
from gastos.models import (
    CentroCosto,
    DecisionGasto,
    EstadoSolicitud,
    PagoExterno,
    SubsanacionGasto,
    TipoFlujoGasto,
)
from gastos.services import (
    ConcurrencyConflictError,
    InvalidDecisionInputError,
    InvalidSubsanacionInputError,
    InvalidTransitionError,
    can_decide_expense,
    corregir_solicitud_gasto,
    decide_expense,
    puede_corregir_solicitud,
    validate_decision_content,
)
from identidad.services import Actor
from tests.soporte_gastos import crear_gasto_sintetico


def _actor(user: Any, caps: set[str]) -> Actor:
    return Actor(subject_id=user.pk, capabilities=frozenset(caps))


def _client_como(user: Any, caps: list[str] | set[str]) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["demo_capabilities"] = sorted(caps)
    session.save()
    return client


@pytest.mark.django_db
def test_observar_matriz_y_validacion_motivo(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_o = _actor(user_o, {"gastos.decidir", "gastos.consultar_todas"})

    gasto = crear_gasto_sintetico(
        concepto="Equipamiento",
        monto_estimado=Decimal("10000.00"),
        unidad_requirente="Depto Sistemas",
        solicitante=user_a,
    )

    assert can_decide_expense(actor_o, gasto, "observar") is True

    with pytest.raises(InvalidDecisionInputError):
        validate_decision_content(action="observar", expected_version=0, motivo="   ")
    with pytest.raises(InvalidDecisionInputError):
        validate_decision_content(action="observar", expected_version=0, motivo="abc\x00def")

    decide_expense(
        actor=actor_o,
        solicitud_id=gasto.pk,
        action="postergar",
        expected_version=0,
        motivo="Falta definir prioridad",
    )
    gasto.refresh_from_db()
    assert gasto.estado == EstadoSolicitud.POSTERGADA
    assert can_decide_expense(actor_o, gasto, "observar") is True

    decide_expense(
        actor=actor_o,
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=1,
        motivo="Corregir concepto y monto",
    )
    gasto.refresh_from_db()
    assert gasto.estado == EstadoSolicitud.OBSERVADA
    assert gasto.version == 2

    for accion in ("aceptar", "observar", "postergar", "rechazar"):
        assert can_decide_expense(actor_o, gasto, accion) is False
    with pytest.raises(InvalidTransitionError):
        decide_expense(
            actor=actor_o,
            solicitud_id=gasto.pk,
            action="aceptar",
            expected_version=2,
            motivo="",
        )


@pytest.mark.django_db(transaction=True)
def test_subsanacion_completa_historial_inmutabilidad_y_concurrencia(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_a = _actor(user_a, {"gastos.presentar", "gastos.consultar_propias"})
    actor_o = _actor(user_o, {"gastos.decidir", "gastos.consultar_todas"})

    cc_viejo = CentroCosto.objects.create(codigo="CC-OLD", nombre="Centro Viejo", activo=True)
    cc_nuevo = CentroCosto.objects.create(codigo="CC-NEW", nombre="Centro Nuevo", activo=True)

    gasto = crear_gasto_sintetico(
        concepto="Concepto inicial",
        monto_estimado=Decimal("1500.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=cc_viejo,
    )
    decide_expense(
        actor=actor_o,
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=0,
        motivo="Detallar equipo e imputar centro nuevo",
    )

    corregida = corregir_solicitud_gasto(
        actor=actor_a,
        solicitud_id=gasto.pk,
        expected_version=1,
        concepto="Concepto corregido",
        monto_estimado=Decimal("2450.50"),
        centro_costo=cc_nuevo,
    )
    corregida.refresh_from_db()
    assert corregida.estado == EstadoSolicitud.PRESENTADA
    assert corregida.version == 2
    assert corregida.concepto == "Concepto corregido"
    assert corregida.monto_estimado == Decimal("2450.50")
    assert corregida.centro_costo_id == cc_nuevo.pk
    assert corregida.tramite_base.centro_costo_codigo == "CC-NEW"
    assert corregida.tipo_flujo == TipoFlujoGasto.COMPRA_DIRECTA
    assert corregida.unidad_requirente == "Laboratorio"
    assert corregida.solicitante_id == user_a.pk

    sub = SubsanacionGasto.objects.get(solicitud=corregida)
    assert sub.concepto_anterior == "Concepto inicial"
    assert sub.concepto_nuevo == "Concepto corregido"
    assert sub.monto_anterior == Decimal("1500.00")
    assert sub.monto_nuevo == Decimal("2450.50")
    assert sub.centro_costo_anterior_id == cc_viejo.pk
    assert sub.centro_costo_nuevo_id == cc_nuevo.pk

    # Inmutabilidad de SubsanacionGasto
    with pytest.raises(IntegrityError):
        SubsanacionGasto.objects.filter(pk=sub.pk).update(concepto_nuevo="Tamper")
    with pytest.raises(IntegrityError):
        SubsanacionGasto.objects.bulk_update([sub], ["concepto_nuevo"])
    with pytest.raises(IntegrityError):
        SubsanacionGasto.objects.filter(pk=sub.pk).delete()
    with pytest.raises(IntegrityError):
        sub.save()
    with pytest.raises(IntegrityError):
        sub.delete()

    # Operador reevalúa tras reenvío y segunda observación admite concurrencia protegida
    decide_expense(
        actor=actor_o,
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=2,
        motivo="Segunda revisión",
    )
    corregir_solicitud_gasto(
        actor=actor_a,
        solicitud_id=gasto.pk,
        expected_version=3,
        concepto="Concepto final",
        monto_estimado=Decimal("3000.00"),
        centro_costo=None,
    )
    with pytest.raises(InvalidTransitionError):
        corregir_solicitud_gasto(
            actor=actor_a,
            solicitud_id=gasto.pk,
            expected_version=3,
            concepto="Reintento ilegal",
            monto_estimado=Decimal("3100.00"),
            centro_costo=None,
        )

    # Versión obsoleta mientras sigue observada -> ConcurrencyConflictError
    decide_expense(
        actor=actor_o,
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=4,
        motivo="Tercera observación",
    )
    with pytest.raises(ConcurrencyConflictError):
        corregir_solicitud_gasto(
            actor=actor_a,
            solicitud_id=gasto.pk,
            expected_version=4,
            concepto="Versión vieja",
            monto_estimado=Decimal("3200.00"),
            centro_costo=None,
        )
    assert SubsanacionGasto.objects.filter(solicitud=gasto).count() == 2


@pytest.mark.django_db
def test_centro_costo_inactivo_actual_vs_otro_y_nulo(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_a = _actor(user_a, {"gastos.presentar", "gastos.consultar_propias"})
    actor_o = _actor(user_o, {"gastos.decidir", "gastos.consultar_todas"})

    cc_actual = CentroCosto.objects.create(codigo="CC-A", nombre="Actual", activo=True)
    cc_otro_inactivo = CentroCosto.objects.create(
        codigo="CC-B", nombre="Otro Inactivo", activo=False
    )

    gasto = crear_gasto_sintetico(
        concepto="Reactivos",
        monto_estimado=Decimal("500.00"),
        unidad_requirente="Química",
        solicitante=user_a,
        centro_costo=cc_actual,
    )
    cc_actual.activo = False
    cc_actual.save(update_fields=["activo"])

    decide_expense(
        actor=actor_o,
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=0,
        motivo="Ajustar monto",
    )

    with pytest.raises(InvalidSubsanacionInputError):
        corregir_solicitud_gasto(
            actor=actor_a,
            solicitud_id=gasto.pk,
            expected_version=1,
            concepto="Reactivos",
            monto_estimado=Decimal("600.00"),
            centro_costo=cc_otro_inactivo.pk,
        )
    with pytest.raises(InvalidSubsanacionInputError):
        corregir_solicitud_gasto(
            actor=actor_a,
            solicitud_id=gasto.pk,
            expected_version=1,
            concepto="Reactivos",
            monto_estimado=Decimal("600.00"),
            centro_costo=999999,
        )

    # Conservar el centro inactivo actual sí está permitido
    corregir_solicitud_gasto(
        actor=actor_a,
        solicitud_id=gasto.pk,
        expected_version=1,
        concepto="Reactivos ajustados",
        monto_estimado=Decimal("600.00"),
        centro_costo=cc_actual.pk,
    )
    gasto.refresh_from_db()
    assert gasto.centro_costo_id == cc_actual.pk


@pytest.mark.django_db
def test_vistas_permisos_guardas_409_datos_conservados_y_cronologia(
    demo_accounts: tuple[dict[str, Any], str],
    create_actor: Any,
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]
    user_o = accounts["demo_o"]

    user_sin_cap, _ = create_actor("titular_sin_cap", ["gastos.consultar_todas"])
    gasto_sin_cap = crear_gasto_sintetico(
        concepto="Sin permiso presentar",
        monto_estimado=Decimal("900.00"),
        unidad_requirente="Administración",
        solicitante=user_sin_cap,
    )
    decide_expense(
        actor=_actor(user_o, {"gastos.decidir", "gastos.consultar_todas"}),
        solicitud_id=gasto_sin_cap.pk,
        action="observar",
        expected_version=0,
        motivo="Revisar concepto",
    )
    client_sin_cap = Client()
    client_sin_cap.force_login(user_sin_cap)
    resp_det_sin = client_sin_cap.get(
        reverse("gastos:detalle", kwargs={"pk": gasto_sin_cap.pk})
    )
    assert resp_det_sin.status_code == 200
    assert (
        "No tenés permiso para corregir y reenviar solicitudes"
        in resp_det_sin.content.decode("utf-8")
    )
    resp_corregir_sin = client_sin_cap.get(
        reverse("gastos:corregir", kwargs={"pk": gasto_sin_cap.pk})
    )
    assert resp_corregir_sin.status_code == 403

    gasto = crear_gasto_sintetico(
        concepto="Papelería",
        monto_estimado=Decimal("1200.00"),
        unidad_requirente="Administración",
        solicitante=user_a,
    )
    decide_expense(
        actor=_actor(user_o, {"gastos.decidir", "gastos.consultar_todas"}),
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=0,
        motivo="Especificar cantidad",
    )

    # Otro usuario sin visibilidad -> 404; operador con visibilidad global sin ser titular -> 403
    client_b = Client()
    client_b.force_login(user_b)
    assert client_b.get(reverse("gastos:corregir", kwargs={"pk": gasto.pk})).status_code == 404
    client_o = Client()
    client_o.force_login(user_o)
    assert client_o.get(reverse("gastos:corregir", kwargs={"pk": gasto.pk})).status_code == 403

    # POST con versión obsoleta conserva valores en el formulario y responde 409
    client_a = _client_como(user_a, ["gastos.presentar", "gastos.consultar_propias"])
    resp_get_corregir = client_a.get(reverse("gastos:corregir", kwargs={"pk": gasto.pk}))
    assert resp_get_corregir.status_code == 200
    html_corregir = resp_get_corregir.content.decode("utf-8")
    assert 'class="solicitud-detalle nueva-solicitud"' in html_corregir
    assert "solicitud_importe.js" in html_corregir
    resp_409 = client_a.post(
        reverse("gastos:corregir", kwargs={"pk": gasto.pk}),
        data={
            "version": "0",
            "concepto": "Papelería resmas x10",
            "monto_estimado": "1850,00",
            "centro_costo": "",
        },
    )
    assert resp_409.status_code == 409
    html_409 = resp_409.content.decode("utf-8")
    assert "Papelería resmas x10" in html_409
    assert "1850,00" in html_409

    # POST válido reenvía y aparece en cronología con etiqueta es-AR
    resp_ok = client_a.post(
        reverse("gastos:corregir", kwargs={"pk": gasto.pk}),
        data={
            "version": "1",
            "concepto": "Papelería resmas x10",
            "monto_estimado": "1850,00",
            "centro_costo": "",
        },
    )
    assert resp_ok.status_code == 302

    # POST inválido sobre solicitud que ya volvió a PRESENTADA responde 409 antes de validar form
    resp_estado_409 = client_a.post(
        reverse("gastos:corregir", kwargs={"pk": gasto.pk}),
        data={"version": "2", "concepto": "", "monto_estimado": "-5"},
    )
    assert resp_estado_409.status_code == 409

    resp_det = client_a.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk}))
    html_det = resp_det.content.decode("utf-8")
    assert "Subsanación de solicitud" in html_det
    assert "1.850,00" in html_det

    # Con PagoExterno existente nunca puede corregir
    gasto.estado = EstadoSolicitud.OBSERVADA
    gasto.save(update_fields=["estado"])
    PagoExterno.objects.create(
        solicitud=gasto,
        importe=Decimal("1000.00"),
        monto_bruto=Decimal("1000.00"),
        monto_retencion_atp=Decimal("0.00"),
        fecha_pago="2026-11-15",
        referencia_externa="REF-1",
        referencia_documental="DOC-1",
        huella_idempotencia="h" * 64,
    )
    actor_a = _actor(user_a, {"gastos.presentar", "gastos.consultar_propias"})
    assert puede_corregir_solicitud(actor_a, gasto) is False


@pytest.mark.django_db(transaction=True)
def test_avisos_observada_y_reenvio_no_emite_nueva_solicitud(
    demo_accounts: tuple[dict[str, Any], str],
    settings: Any,
) -> None:
    settings.AVISOS_EMAIL_ENABLED = False
    mail.outbox.clear()
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    user_a.email = "titular@example.test"
    user_a.save(update_fields=["email"])

    gasto = crear_gasto_sintetico(
        concepto="Servicio técnico",
        monto_estimado=Decimal("4000.00"),
        unidad_requirente="Taller",
        solicitante=user_a,
    )
    decide_expense(
        actor=_actor(user_o, {"gastos.decidir", "gastos.consultar_todas"}),
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=0,
        motivo="Adjuntar detalle",
    )
    decision = DecisionGasto.objects.get(
        solicitud=gasto, estado_resultante=EstadoSolicitud.OBSERVADA
    )
    assert decision.get_estado_resultante_display() == "Observada"

    aviso = Aviso.objects.filter(
        destinatario=user_a,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        decision_id=decision.pk,
    ).first()
    assert aviso is not None
    assert IntencionCorreo.objects.filter(aviso=aviso).count() == 0
    assert len(mail.outbox) == 0

    # Reenvío no genera aviso nueva_solicitud_gasto para operadores
    avisos_previos = Aviso.objects.filter(
        solicitud_id=gasto.pk,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
    ).count()
    corregir_solicitud_gasto(
        actor=_actor(user_a, {"gastos.presentar", "gastos.consultar_propias"}),
        solicitud_id=gasto.pk,
        expected_version=1,
        concepto="Servicio técnico detallado",
        monto_estimado=Decimal("4000.00"),
        centro_costo=None,
    )
    avisos_post = Aviso.objects.filter(
        solicitud_id=gasto.pk,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
    ).count()
    assert avisos_post == avisos_previos
    assert generar_aviso_decision_gasto(decision.pk, preparar_correo=False) == 0


@pytest.mark.django_db(transaction=True)
def test_concurrencia_real_subsanacion_postgresql(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """Concurrencia real en PostgreSQL: dos subsanaciones simultáneas a la misma versión."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]

    gasto = crear_gasto_sintetico(
        concepto="Equipamiento laboratorio",
        monto_estimado=Decimal("10000.00"),
        unidad_requirente="Física",
        solicitante=user_a,
    )
    decide_expense(
        actor=_actor(user_o, {"gastos.decidir", "gastos.consultar_todas"}),
        solicitud_id=gasto.pk,
        action="observar",
        expected_version=0,
        motivo="Detallar equipamiento",
    )

    url = reverse("gastos:corregir", kwargs={"pk": gasto.pk})
    barrier = Barrier(2)
    results: list[int | Exception | None] = [None, None]
    payloads = [
        {
            "version": "1",
            "concepto": "Equipamiento laboratorio lote A",
            "monto_estimado": "10500,00",
            "centro_costo": "",
        },
        {
            "version": "1",
            "concepto": "Equipamiento laboratorio lote B",
            "monto_estimado": "11250,00",
            "centro_costo": "",
        },
    ]

    def worker(idx: int) -> None:
        connections.close_all()
        try:
            client = Client()
            client.force_login(user_a)
            barrier.wait(timeout=10)
            resp = client.post(url, payloads[idx])
            results[idx] = resp.status_code
        except Exception as exc:
            results[idx] = exc
        finally:
            connections.close_all()

    t1 = Thread(target=worker, args=(0,))
    t2 = Thread(target=worker, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not t1.is_alive(), "El hilo 1 quedó bloqueado."
    assert not t2.is_alive(), "El hilo 2 quedó bloqueado."

    status_codes = sorted(r for r in results if isinstance(r, int))
    assert status_codes == [302, 409], f"Resultados inesperados de concurrencia: {results}"

    winner_idx = results.index(302)
    expected_concepto = payloads[winner_idx]["concepto"]
    expected_monto = (
        Decimal("10500.00") if winner_idx == 0 else Decimal("11250.00")
    )

    gasto.refresh_from_db()
    assert gasto.estado == EstadoSolicitud.PRESENTADA
    assert gasto.version == 2
    assert gasto.concepto == expected_concepto
    assert gasto.monto_estimado == expected_monto

    subsanaciones = SubsanacionGasto.objects.filter(solicitud=gasto)
    assert subsanaciones.count() == 1
    assert subsanaciones.first().autor == user_a
