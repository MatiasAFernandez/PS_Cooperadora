"""Contexto compartido de tarjetas y saludo para la pantalla de Inicio según rol."""

from __future__ import annotations

from django.http import HttpRequest
from django.urls import reverse

from identidad.models import CuentaLocal
from identidad.services import Actor


def nombre_saludo(request: HttpRequest, cuenta: CuentaLocal | None = None) -> str:
    """Devolver el nombre visible del usuario con fallback seguro, sin 'Hola, .'."""
    candidatos = [
        cuenta.nombre_completo if cuenta is not None else "",
        request.user.get_full_name() if request.user.is_authenticated else "",
        request.user.get_username() if request.user.is_authenticated else "",
    ]
    for valor in candidatos:
        limpio = (valor or "").strip()
        if limpio:
            return limpio
    return ""


def tarjetas_inicio(actor: Actor, *, es_cuenta_local: bool) -> list[dict[str, str]]:
    """Construir accesos directos acordes a las capacidades vigentes del actor."""
    caps = actor.capabilities
    tarjetas: list[dict[str, str]] = []

    if "gastos.consultar_todas" in caps:
        tarjetas.append(
            {
                "grupo": "Trámites",
                "titulo": "Solicitudes de gasto",
                "descripcion": "Decisiones, pagos registrados y seguimiento documental.",
                "cta": "Ir a Gastos",
                "url": reverse("gastos:lista"),
            }
        )
    elif "gastos.consultar_propias" in caps:
        tarjetas.append(
            {
                "grupo": "Trámites",
                "titulo": "Mis solicitudes de gasto",
                "descripcion": (
                    "Consultá tus solicitudes presentadas y realizá pedidos de compra o reintegro."
                ),
                "cta": "Ir a Gastos",
                "url": reverse("gastos:lista"),
            }
        )
    elif "gastos.presentar" in caps:
        tarjetas.append(
            {
                "grupo": "Trámites",
                "titulo": "Presentar solicitud de gasto",
                "descripcion": (
                    "Iniciá un nuevo pedido de compra directa o reintegro ante Cooperadora."
                ),
                "cta": "Nueva solicitud",
                "url": reverse("gastos:presentar"),
            }
        )

    if "facturacion.consultar_todas" in caps:
        tarjetas.append(
            {
                "grupo": "Trámites",
                "titulo": "Solicitudes de facturación",
                "descripcion": "Emisión de comprobantes externos, revisión de respaldos y cobros.",
                "cta": "Ir a Facturación",
                "url": reverse("facturacion:lista"),
            }
        )
    elif "facturacion.consultar_propias" in caps:
        tarjetas.append(
            {
                "grupo": "Trámites",
                "titulo": "Mis solicitudes de facturación",
                "descripcion": (
                    "Consultá tus trámites de facturación, comprobantes e informes de cobro."
                ),
                "cta": "Ir a Facturación",
                "url": reverse("facturacion:lista"),
            }
        )
    elif "facturacion.presentar" in caps:
        tarjetas.append(
            {
                "grupo": "Trámites",
                "titulo": "Presentar solicitud de facturación",
                "descripcion": "Cargá los datos necesarios para que Cooperadora emita la factura.",
                "cta": "Nueva solicitud",
                "url": reverse("facturacion:presentar"),
            }
        )

    if "gastos.consultar_propias" in caps or "gastos.consultar_todas" in caps:
        tarjetas.append(
            {
                "grupo": "Seguimiento",
                "titulo": "Avisos",
                "descripcion": (
                    "Novedades sobre decisiones y pagos registrados en solicitudes de gasto."
                ),
                "cta": "Ver avisos",
                "url": reverse("avisos:lista"),
            }
        )

    if "gastos.consultar_todas" in caps or "facturacion.consultar_todas" in caps:
        url_reporte = (
            reverse("gestion:reporte_gastos")
            if "gastos.consultar_todas" in caps
            else reverse("gestion:reporte_facturacion")
        )
        tarjetas.append(
            {
                "grupo": "Gestión",
                "titulo": "Reportes",
                "descripcion": "Resumen económico, compromisos y evolución por período.",
                "cta": "Ver reportes",
                "url": url_reporte,
            }
        )

    if (
        "gestion.configurar" in caps
        or "gastos.decidir" in caps
        or "gastos.registrar_pago" in caps
    ):
        url_config = (
            reverse("gestion:configuracion", args=["GASTO"])
            if "gestion.configurar" in caps
            else reverse("gastos:gestion_catalogos")
        )
        tarjetas.append(
            {
                "grupo": "Gestión",
                "titulo": "Configuración",
                "descripcion": "Centros de costo, parámetros operativos y campos configurables.",
                "cta": "Abrir configuración",
                "url": url_config,
            }
        )

    if es_cuenta_local and "identidad.administrar_cuentas" in caps:
        tarjetas.append(
            {
                "grupo": "Administración",
                "titulo": "Solicitudes de cuenta",
                "descripcion": "Evaluá solicitudes de alta pendientes y confirmá su habilitación.",
                "cta": "Revisar solicitudes",
                "url": reverse("cuentas:altas"),
            }
        )
        tarjetas.append(
            {
                "grupo": "Administración",
                "titulo": "Usuarios locales",
                "descripcion": "Consultá cuentas registradas, datos, perfiles y estado de acceso.",
                "cta": "Gestionar usuarios",
                "url": reverse("cuentas:usuarios"),
            }
        )

    if es_cuenta_local:
        tarjetas.append(
            {
                "grupo": "Cuenta",
                "titulo": "Mi cuenta",
                "descripcion": "Gestioná la seguridad y actualizá tu contraseña de acceso.",
                "cta": "Cambiar contraseña",
                "url": reverse("cuentas:cambiar_clave"),
            }
        )

    return tarjetas


def contexto_inicio(
    request: HttpRequest,
    actor: Actor,
    *,
    cuenta: CuentaLocal | None = None,
    acceso_local: bool = False,
) -> dict[str, object]:
    """Construir el contexto unificado de Inicio para cuentas locales y demo."""
    tarjetas = tarjetas_inicio(actor, es_cuenta_local=acceso_local)
    tiene_circuitos = any(
        cap in actor.capabilities
        for cap in (
            "gastos.presentar",
            "gastos.consultar_propias",
            "gastos.consultar_todas",
            "facturacion.presentar",
            "facturacion.consultar_propias",
            "facturacion.consultar_todas",
            "identidad.administrar_cuentas",
        )
    )
    return {
        "actor": actor,
        "cuenta": cuenta,
        "acceso_local": acceso_local,
        "nombre_saludo": nombre_saludo(request, cuenta),
        "tarjetas_inicio": tarjetas,
        "sin_circuitos_operativos": not tiene_circuitos,
    }
