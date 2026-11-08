"""Vistas para el circuito de gastos."""

from decimal import Decimal
from typing import Any

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q, Subquery
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from comunes.models import Circuito
from documentos.models import Documento
from documentos.operaciones import operacion_documental
from documentos.policy import ArchivoInvalido, validar_archivo
from documentos.services import (
    TIPOS_POR_CIRCUITO,
    AlmacenamientoNoDisponible,
    DocumentoNoVisible,
    incorporar,
)
from gastos.auth import has_capability, resolve_actor
from gastos.contracts import (
    DocumentVerificationError,
    OpcionDocumental,
    tipos_documento_admitidos_para_flujo,
)
from gastos.datos_transferencia import (
    DatosTransferenciaBloqueadaError,
    DatosTransferenciaInvalidInputError,
    DatosTransferenciaNotFoundError,
    DatosTransferenciaPermissionDeniedError,
    centro_costo_transferencia_por_defecto,
    consultar_revisiones_datos_transferencia,
    datos_de_revision,
    puede_editar_datos_transferencia,
    registrar_revision_datos_transferencia,
)
from gastos.document_provider import cargar_proveedor_documental
from gastos.forms import (
    CentroCostoForm,
    ConstanciaATPForm,
    DatosTransferenciaForm,
    DecisionGastoForm,
    DocumentoGastoForm,
    FiltroEstadoGastoForm,
    PagoExternoForm,
    ParametrosATPForm,
    RectificacionPagoForm,
    RespaldoSolicitudForm,
    SolicitudGastoForm,
)
from gastos.models import (
    CentroCosto,
    DecisionGasto,
    EstadoSolicitud,
    EventoPagoExterno,
    PagoExterno,
    TipoFlujoGasto,
)
from gastos.payments import (
    PaymentConflictError,
    PaymentExpenseNotFoundError,
    PaymentInvalidExpenseStateError,
    PaymentInvalidInputError,
    PaymentPermissionDeniedError,
    PaymentVersionConflictError,
    consultar_cambios_pago,
    consultar_pago_externo,
    derivar_categoria_respaldo,
    incorporar_constancia_atp_posterior,
    rectificar_pago_externo,
    registrar_pago_externo,
)
from gastos.proyeccion_documental import (
    TIPOS_RESPALDO_COMERCIAL,
    obtener_versiones_reemplazables_titular,
    proyectar_documentos,
    proyectar_respaldos_titular,
)
from gastos.queries import visible_expenses
from gastos.reports import (
    obtener_pendientes_actuales_gastos,
    obtener_reporte_cuatrimestral_gastos,
)
from gastos.services import (
    ConcurrencyConflictError,
    DeudaDocumentalBloqueoError,
    ExpenseNotFoundError,
    ExpensePermissionDeniedError,
    InvalidDecisionInputError,
    InvalidTransitionError,
    actualizar_parametros_atp,
    can_decide_expense,
    crear_solicitud_gasto,
    decide_expense,
    obtener_alicuota_atp,
    obtener_base_imponible_atp,
    verificar_deuda_documental_solicitante,
)


def _enforce_actor(request: HttpRequest) -> Any:
    """Verifica la presencia de un actor activo.

    Si no hay actor:
    - Con demo habilitada: redirige al acceso de demo.
    - Con demo deshabilitada: deniega con 403 Forbidden sin ofrecer login.
    """
    actor = resolve_actor(request)
    if actor is not None:
        return actor

    demo_enabled = getattr(settings, "DEMO_IDENTITY_ENABLED", False)
    if demo_enabled:
        return redirect_to_login(request.get_full_path())

    raise PermissionDenied("Identidad no configurada o demo deshabilitada.")


def _pago_externo_registrado(solicitud: Any) -> bool:
    """Indica si el gasto visible ya posee un pago externo persistido."""
    return PagoExterno.objects.filter(solicitud_id=solicitud.pk).exists()


def _servicio_pago_no_disponible() -> HttpResponse:
    """Respuesta genérica fail-closed cuando falta el proveedor o su listado."""
    return HttpResponse(
        "El registro de pago no está disponible en este entorno.",
        status=503,
    )


def _listar_opciones_documentales(
    proveedor: Any, actor: Any, solicitud: Any
) -> list[OpcionDocumental] | None:
    """Consulta y valida el listado seguro del proveedor para el gasto visible."""
    tipos_admitidos = tipos_documento_admitidos_para_flujo(
        getattr(solicitud, "tipo_flujo", None)
    )
    try:
        opciones = list(
            proveedor.listar_opciones_para_pago(
                actor=actor,
                gasto=solicitud,
                tipos_admitidos=tipos_admitidos,
            )
        )
    except Exception:
        # Un listado que falla no habilita ningún registro: fail-closed (503).
        return None

    referencias: set[str] = set()
    for opcion in opciones:
        referencia = getattr(opcion, "referencia_documental", None)
        tipo = getattr(opcion, "tipo_documento", None)
        etiqueta = getattr(opcion, "etiqueta", None)
        if not isinstance(referencia, str) or not referencia.strip():
            return None
        if "\x00" in referencia or len(referencia) > 255 or referencia in referencias:
            return None
        if tipo not in tipos_admitidos:
            return None
        if not isinstance(etiqueta, str) or not etiqueta.strip():
            return None
        referencias.add(referencia)

    return opciones


def _cargar_opciones_documentales(
    actor: Any, solicitud: Any
) -> tuple[Any, list[OpcionDocumental]] | None:
    """Carga el proveedor de servidor y su listado seguro de opciones.

    Devuelve `None` (fail-closed) si el proveedor no está configurado, no cumple
    el puerto, lanza un error o entrega opciones que no respetan el contrato.
    El proveedor proviene exclusivamente de la configuración de servidor,
    nunca del POST.
    """
    proveedor = cargar_proveedor_documental()
    if proveedor is None:
        return None

    opciones = _listar_opciones_documentales(proveedor, actor, solicitud)
    if opciones is None:
        return None

    return proveedor, opciones


def _combinaciones_documentales_para_aporte(
    actor: Any, solicitud: Any = None
) -> dict[str, tuple[str, ...]]:
    """Limita las opciones visibles a respaldos comerciales ya admitidos."""
    combinaciones = TIPOS_POR_CIRCUITO[Circuito.GASTO]
    personal = has_capability(actor, "gastos.consultar_todas")
    resultado: dict[str, tuple[str, ...]] = {}
    for tipo, procedencias in combinaciones.items():
        if tipo not in TIPOS_RESPALDO_COMERCIAL:
            continue
        if (
            tipo == Documento.Tipo.PRESUPUESTO_PROFORMA
            and getattr(solicitud, "tipo_flujo", None) == TipoFlujoGasto.REINTEGRO
        ):
            continue
        permitidas = tuple(
            procedencia
            for procedencia in sorted(procedencias)
            if (
                procedencia != Documento.Procedencia.SOLICITANTE
                if personal
                else procedencia == Documento.Procedencia.SOLICITANTE
            )
        )
        if permitidas:
            resultado[tipo] = permitidas
    return resultado


def _formulario_aporte_documental(
    actor: Any,
    solicitud: Any,
    *,
    data: Any = None,
    files: Any = None,
    preseleccionar_reemplaza_id: Any = None,
) -> tuple[DocumentoGastoForm, tuple[Any, ...]]:
    """Arma opciones de reemplazo sólo desde la proyección documental autorizada."""
    combinaciones = _combinaciones_documentales_para_aporte(actor, solicitud)
    proyeccion = proyectar_documentos(actor, solicitud)
    if proyeccion is not None:
        versiones_reemplazables = tuple(
            version
            for version in proyeccion.versiones
            if version.vigente
            and version.tipo in combinaciones
        )
    elif actor is not None and getattr(actor, "subject_id", None) == solicitud.solicitante_id:
        versiones_reemplazables = obtener_versiones_reemplazables_titular(
            actor, solicitud, combinaciones
        )
    else:
        versiones_reemplazables = ()

    initial = {}
    if preseleccionar_reemplaza_id is not None and data is None:
        version_preseleccionada = next(
            (
                v
                for v in versiones_reemplazables
                if str(v.documento_id) == str(preseleccionar_reemplaza_id)
            ),
            None,
        )
        if version_preseleccionada is not None:
            initial["reemplaza_id"] = str(version_preseleccionada.documento_id)
            initial["tipo"] = version_preseleccionada.tipo

    form = DocumentoGastoForm(
        data=data,
        files=files,
        initial=initial or None,
        combinaciones_documentales=combinaciones,
        versiones_reemplazables=versiones_reemplazables,
    )
    return form, versiones_reemplazables


def _contexto_formulario_aporte(
    actor: Any,
    solicitud: Any,
    form: DocumentoGastoForm,
    versiones_reemplazables: tuple[Any, ...],
) -> dict[str, Any]:
    return {
        "actor": actor,
        "solicitud": solicitud,
        "form": form,
        "versiones_reemplazables": versiones_reemplazables,
        "puede_ver_documentos": has_capability(actor, "documentos.consultar_metadatos"),
    }


def _puede_adjuntar_respaldo(actor: Any) -> bool:
    """Adjuntar exige aporte documental y visibilidad propia o global."""
    return has_capability(actor, "documentos.incorporar") and (
        has_capability(actor, "gastos.consultar_propias")
        or has_capability(actor, "gastos.consultar_todas")
    )


def _carga_respaldo_multiple(request: HttpRequest) -> bool:
    """El alta acepta a lo sumo un archivo en el campo acordado."""
    if not request.FILES:
        return False
    return (
        set(request.FILES.keys()) != {"respaldo_archivo"}
        or len(request.FILES.getlist("respaldo_archivo")) != 1
    )


def _max_upload_mib() -> int:
    max_bytes = getattr(settings, "DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)
    return max(1, int(max_bytes / (1024 * 1024)))


class SolicitudGastoCreateView(View):
    """Presentación de una nueva solicitud de gasto."""

    @staticmethod
    def _contexto(
        actor: Any,
        form: SolicitudGastoForm,
        datos_form: DatosTransferenciaForm,
        respaldo_form: RespaldoSolicitudForm,
        resumen_deuda: Any,
    ) -> dict[str, Any]:
        return {
            "form": form,
            "datos_form": datos_form,
            "respaldo_form": respaldo_form,
            "actor": actor,
            "resumen_deuda": resumen_deuda,
            "puede_adjuntar_respaldo": _puede_adjuntar_respaldo(actor),
            "max_upload_mib": _max_upload_mib(),
        }

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.presentar"):
            raise PermissionDenied("No posee capacidad para presentar gastos.")

        resumen_deuda = verificar_deuda_documental_solicitante(actor)
        form = SolicitudGastoForm()
        datos_form = DatosTransferenciaForm()
        respaldo_form = RespaldoSolicitudForm()
        return render(
            request,
            "gastos/solicitud_form.html",
            self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.presentar"):
            raise PermissionDenied("No posee capacidad para presentar gastos.")

        if request.FILES and not _puede_adjuntar_respaldo(actor):
            raise PermissionDenied("No posee permiso para adjuntar el respaldo.")

        resumen_deuda = verificar_deuda_documental_solicitante(actor)

        cc_list = request.POST.getlist("centro_costo")
        cc_catalog_raw = ""
        cc_transfer_raw = ""
        if len(cc_list) >= 2:
            cc_catalog_raw = (cc_list[0] or "").strip()
            cc_transfer_raw = (cc_list[1] or "").strip()
        elif len(cc_list) == 1:
            val = (cc_list[0] or "").strip()
            if (
                val
                and val.isdigit()
                and CentroCosto.objects.filter(pk=int(val), activo=True).exists()
            ):
                cc_catalog_raw = val
            else:
                cc_transfer_raw = val

        cc = None
        centro_costo_nombre = ""
        if cc_catalog_raw and cc_catalog_raw.isdigit():
            try:
                cc = CentroCosto.objects.filter(pk=int(cc_catalog_raw), activo=True).first()
                if cc:
                    centro_costo_nombre = cc.nombre
            except (ValueError, TypeError):
                cc = None

        solicitud_post = request.POST.copy()
        if cc is not None:
            solicitud_post["centro_costo"] = str(cc.pk)
        elif cc_catalog_raw:
            solicitud_post["centro_costo"] = cc_catalog_raw
        else:
            solicitud_post["centro_costo"] = ""

        form = SolicitudGastoForm(solicitud_post)

        tiene_datos_bancarios = any(
            (request.POST.get(c) or "").strip()
            for c in ("titular_nombre", "identificacion", "cbu_alias", "correo_comprobante")
        )
        if tiene_datos_bancarios:
            datos_post = request.POST.copy()
            if cc_transfer_raw and (cc is None or cc_transfer_raw != str(cc.pk)):
                datos_post["centro_costo"] = cc_transfer_raw
            elif cc is not None:
                datos_post["centro_costo"] = cc.nombre
            else:
                datos_post["centro_costo"] = ""

            datos_form = DatosTransferenciaForm(
                datos_post,
                centro_costo_default=centro_costo_nombre,
            )
        else:
            datos_form = DatosTransferenciaForm({})

        respaldo_form = RespaldoSolicitudForm(request.POST, request.FILES)
        # La limpieza previa evita que full_clean descarte el error de cantidad.
        respaldo_form.is_valid()
        error_carga = (
            "Adjuntá un solo archivo de respaldo."
            if _carga_respaldo_multiple(request)
            else ""
        )
        if error_carga:
            respaldo_form.add_error("respaldo_archivo", error_carga)

        if resumen_deuda.tiene_bloqueo:
            form.add_error(
                None,
                f"Presentación bloqueada: Registrás {resumen_deuda.total_en_mora} compras directas "
                f"con rendición de factura definitiva vencida "
                f"(más de {resumen_deuda.dias_gracia} días). "
                f"Debés regularizar los comprobantes pendientes antes de presentar nuevas.",
            )
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=400,
            )

        form_valido = form.is_valid()
        datos_valido = datos_form.is_valid()
        if error_carga or not (form_valido and datos_valido):
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=400 if error_carga else 200,
            )

        if not respaldo_form.is_valid():
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=400,
            )

        archivo_subido = respaldo_form.cleaned_data.get("respaldo_archivo")
        archivo = None
        if archivo_subido:
            try:
                archivo = validar_archivo(archivo_subido)
            except ArchivoInvalido as exc:
                respaldo_form.add_error("respaldo_archivo", str(exc))
                return render(
                    request,
                    "gastos/solicitud_form.html",
                    self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                    status=400,
                )

        try:
            if archivo is None:
                solicitud = crear_solicitud_gasto(
                    actor=actor,
                    concepto=form.cleaned_data["concepto"],
                    monto_estimado=form.cleaned_data["monto_estimado"],
                    unidad_requirente=form.cleaned_data["unidad_requirente"],
                    tipo_flujo=form.cleaned_data.get(
                        "tipo_flujo", TipoFlujoGasto.COMPRA_DIRECTA
                    ),
                    centro_costo=form.cleaned_data.get("centro_costo"),
                    datos_transferencia=datos_form.datos_transferencia,
                )
            else:
                # El tipo se deriva de la modalidad ya validada, nunca del POST.
                tipo_respaldo = (
                    Documento.Tipo.FACTURA_PROVEEDOR
                    if form.cleaned_data.get("tipo_flujo") == TipoFlujoGasto.REINTEGRO
                    else Documento.Tipo.PRESUPUESTO_PROFORMA
                )
                with operacion_documental() as escrituras:
                    solicitud = crear_solicitud_gasto(
                        actor=actor,
                        concepto=form.cleaned_data["concepto"],
                        monto_estimado=form.cleaned_data["monto_estimado"],
                        unidad_requirente=form.cleaned_data["unidad_requirente"],
                        tipo_flujo=form.cleaned_data.get(
                            "tipo_flujo", TipoFlujoGasto.COMPRA_DIRECTA
                        ),
                        centro_costo=form.cleaned_data.get("centro_costo"),
                        datos_transferencia=datos_form.datos_transferencia,
                    )
                    incorporar(
                        actor=actor,
                        referencia=f"gastos:{solicitud.pk}",
                        archivo=archivo,
                        tipo=tipo_respaldo,
                        procedencia=Documento.Procedencia.SOLICITANTE,
                        _escrituras=escrituras,
                    )
        except DeudaDocumentalBloqueoError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=400,
            )
        except DatosTransferenciaInvalidInputError as exc:
            datos_form.add_error(None, str(exc))
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=400,
            )
        except ArchivoInvalido as exc:
            if archivo is None:
                raise
            respaldo_form.add_error("respaldo_archivo", str(exc))
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=400,
            )
        except OSError:
            if archivo is None:
                raise
            respaldo_form.add_error(
                "respaldo_archivo",
                "No se pudo guardar el archivo; la solicitud no quedó presentada. "
                "Volvé a elegir el respaldo.",
            )
            return render(
                request,
                "gastos/solicitud_form.html",
                self._contexto(actor, form, datos_form, respaldo_form, resumen_deuda),
                status=503,
            )

        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))


# Límite superior de un pk BigAutoField de PostgreSQL.
_MAX_ID_SOLICITUD_GASTO = 9_223_372_036_854_775_807


def _numero_de_solicitud_buscado(texto: str) -> int | None:
    """Extrae un número de solicitud sólo si es seguro para el pk BigAutoField."""
    digitos = texto[1:] if texto.startswith("#") else texto
    if len(digitos) > 19 or not (digitos.isascii() and digitos.isdigit()):
        return None
    numero = int(digitos)
    if not numero or numero > _MAX_ID_SOLICITUD_GASTO:
        return None
    return numero


class SolicitudGastoListView(View):
    """Listado de solicitudes de gasto visibles para el actor (panel compacto Master-Detail)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        puede_decidir = has_capability(actor, "gastos.decidir")
        puede_pagar = all(
            has_capability(actor, capacidad)
            for capacidad in (
                "gastos.registrar_pago", "gastos.consultar_todas",
                "documentos.ver_metadatos", "documentos.incorporar",
            )
        )
        vista_rapida = puede_decidir or has_capability(actor, "gastos.registrar_pago")
        puede_presentar = has_capability(actor, "gastos.presentar")
        ofrece_atencion = puede_decidir or puede_pagar

        resumen_deuda = verificar_deuda_documental_solicitante(actor) if puede_presentar else None
        deuda_ids = (
            {item.solicitud_id for item in resumen_deuda.solicitudes_pendientes}
            if resumen_deuda else set()
        )

        en_revision = Q(estado__in=(EstadoSolicitud.PRESENTADA, EstadoSolicitud.POSTERGADA))
        sin_pago = Q(estado=EstadoSolicitud.ACEPTADA, pago_externo__isnull=True)
        sin_atp = Q(
            estado=EstadoSolicitud.ACEPTADA,
            pago_externo__monto_retencion_atp__gt=0,
            pago_externo__constancia_atp__isnull=True,
        )
        condiciones_pendiente: dict[str, Q] = {}
        atencion = Q(pk__in=[])
        if puede_decidir:
            decision = en_revision & ~Q(solicitante_id=actor.subject_id)
            condiciones_pendiente["decision"] = decision
            atencion |= decision
        if puede_pagar:
            condiciones_pendiente["pago"] = sin_pago
            condiciones_pendiente["atp"] = sin_atp
            atencion |= sin_pago | sin_atp
        if puede_presentar:
            condiciones_pendiente["deuda"] = Q(pk__in=deuda_ids)

        cualquier_pendiente = Q(pk__in=[])
        for condicion in condiciones_pendiente.values():
            cualquier_pendiente |= condicion
        if condiciones_pendiente:
            condiciones_pendiente["cualquiera"] = cualquier_pendiente

        base_solicitudes = visible_expenses(actor)
        total_atencion = (
            base_solicitudes.filter(atencion).count() if ofrece_atencion else None
        )

        solicitudes = base_solicitudes.select_related("centro_costo", "pago_externo")
        solo_atencion = vista_rapida and request.GET.get("atencion") == "1"
        if solo_atencion:
            solicitudes = solicitudes.filter(atencion)
        if vista_rapida:
            motivo = DecisionGasto.objects.filter(
                solicitud_id=OuterRef("pk"), estado_resultante=OuterRef("estado")
            ).order_by("-fecha", "-pk").values("motivo")[:1]
            solicitudes = solicitudes.select_related("solicitante").annotate(
                motivo_bandeja=Subquery(motivo)
            )
        opciones_pendiente = [
            (clave, etiqueta)
            for clave, etiqueta in (
                ("decision", "Pendiente de decisión"),
                ("pago", "Sin pago registrado"),
                ("atp", "Constancia ATP pendiente"),
                ("deuda", "Falta factura definitiva"),
            )
            if clave in condiciones_pendiente
        ]
        filtro_form = FiltroEstadoGastoForm(request.GET, pendientes=opciones_pendiente)
        if filtro_form.is_valid():
            solicitudes = filtro_form.filtrar_fecha(solicitudes, "fecha_creacion")
            estado = filtro_form.cleaned_data["estado"]
            if estado == "pagada":
                solicitudes = solicitudes.filter(
                    estado=EstadoSolicitud.ACEPTADA, pago_externo__isnull=False
                )
            elif estado:
                solicitudes = solicitudes.filter(estado=estado)
            concepto = filtro_form.cleaned_data["q"]
            if concepto:
                criterio = Q(concepto__icontains=concepto)
                numero = _numero_de_solicitud_buscado(concepto)
                if numero is not None:
                    criterio |= Q(pk=numero)
                solicitudes = solicitudes.filter(criterio)
            pendiente = filtro_form.cleaned_data["pendiente"]
            if pendiente:
                solicitudes = solicitudes.filter(condiciones_pendiente[pendiente])
        else:
            solicitudes = solicitudes.none()

        paginator = Paginator(solicitudes, 25)
        page_number = request.GET.get("page") or request.GET.get("pagina")
        page_obj = paginator.get_page(page_number)

        for s in page_obj:
            s.accion_bandeja = "Ver detalle"
            s.ancla_bandeja = ""
            s.pendiente_bandeja = ""
            s.pagada_bandeja = (
                s.estado == EstadoSolicitud.ACEPTADA
                and getattr(s, "pago_externo", None) is not None
            )
            if s.pk in deuda_ids:
                s.pendiente_bandeja = "Falta factura definitiva"
                s.ancla_bandeja = "#seguimiento-factura"
            elif puede_decidir and s.solicitante_id != actor.subject_id and s.estado in (
                EstadoSolicitud.PRESENTADA, EstadoSolicitud.POSTERGADA,
            ):
                s.pendiente_bandeja = "Pendiente de decisión"
                s.accion_bandeja = "Revisar solicitud"
                s.ancla_bandeja = "#decision-solicitud"
            elif puede_pagar and s.estado == EstadoSolicitud.ACEPTADA:
                pago = getattr(s, "pago_externo", None)
                if pago is None:
                    s.pendiente_bandeja = "Sin pago registrado"
                    s.accion_bandeja = "Revisar pago"
                    s.ancla_bandeja = "#pago-externo"
                elif pago.constancia_atp_pendiente:
                    s.pendiente_bandeja = "Constancia ATP pendiente"
                    s.accion_bandeja = "Ver pago"
                    s.ancla_bandeja = "#pago-externo"

        parametros = request.GET.copy()
        parametros.pop("page", None)
        parametros.pop("pagina", None)

        return render(
            request,
            "gastos/solicitud_list.html",
            {
                "solicitudes": page_obj,
                "page_obj": page_obj,
                "is_paginated": page_obj.has_other_pages(),
                "filtros_query": parametros.urlencode(),
                "actor": actor,
                "filtro_form": filtro_form,
                "resumen_deuda": resumen_deuda,
                "vista_rapida": vista_rapida,
                "puede_presentar": puede_presentar,
                "solo_atencion": solo_atencion,
                "ofrece_atencion": ofrece_atencion,
                "total_atencion": total_atencion,
                "consulta_bandeja": request.GET.urlencode(),
            },
        )


class ReporteCuatrimestralGastosView(View):
    """Vista de agregación directiva de montos solicitados y erogados (GAST-R08)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.consultar_todas"):
            raise PermissionDenied(
                "No posee capacidad para consultar el reporte directivo de gastos."
            )

        anio_param = request.GET.get("anio") or request.GET.get("year")
        anio = None
        if anio_param:
            try:
                anio = int(anio_param)
            except (ValueError, TypeError):
                anio = None

        corte = request.GET.get("corte") or "ANIO"
        modalidad = request.GET.get("modalidad") or ""
        centros_costo_opciones = list(CentroCosto.objects.order_by("codigo", "nombre"))
        centro_param = request.GET.get("centro_costo", "").strip()
        centro_costo_id = next(
            (centro.pk for centro in centros_costo_opciones if str(centro.pk) == centro_param),
            None,
        )
        mostrar_sin_actividad = request.GET.get("sin_actividad") == "1"
        reporte = obtener_reporte_cuatrimestral_gastos(
            anio,
            corte=corte,
            modalidad=modalidad,
            centro_costo_id=centro_costo_id,
        )
        centros_costo_top = sorted(
            (centro for centro in reporte.centros_costo if centro.monto_erogado_bruto > 0),
            key=lambda centro: (-centro.monto_erogado_bruto, centro.codigo, centro.nombre),
        )[:6]
        centros_costo_tabla = [
            centro
            for centro in reporte.centros_costo
            if centro.cantidad_solicitudes
            or centro.cantidad_pagos
            or (centro.centro_costo_id is not None and (mostrar_sin_actividad or centro_costo_id))
        ]

        return render(
            request,
            "gastos/reporte_cuatrimestral.html",
            {
                "actor": actor,
                "reporte": reporte,
                "anio_seleccionado": reporte.anio,
                "corte": reporte.corte,
                "modalidad": reporte.modalidad,
                "centro_costo_seleccionado": str(centro_costo_id) if centro_costo_id else "",
                "centros_costo_opciones": centros_costo_opciones,
                "centros_costo_top": centros_costo_top,
                "centros_costo_tabla": centros_costo_tabla,
                "mostrar_sin_actividad": mostrar_sin_actividad,
                "periodo_label": reporte.periodo_label,
                "pendientes_actuales": obtener_pendientes_actuales_gastos(),
            },
        )


def _solicitud_detail_context(
    actor: Any,
    solicitud: Any,
    detalle_aporte_form: DocumentoGastoForm | None = None,
    detalle_aporte_versiones: tuple[Any, ...] | None = None,
    detalle_aporte_con_error: bool = False,
    preseleccionar_reemplaza_id: Any = None,
    detalle_datos_transferencia_form: DatosTransferenciaForm | None = None,
    detalle_datos_transferencia_con_error: bool = False,
) -> dict[str, Any]:
    """Construye el contexto compartido por el detalle y sus errores de decisión."""
    decisiones = list(solicitud.decisiones.order_by("fecha", "id"))
    pago_consulta = consultar_pago_externo(actor=actor, solicitud_id=solicitud.pk)
    cronologia = [decision.como_historial() for decision in decisiones]
    if pago_consulta is not None:
        evento_pago = (
            EventoPagoExterno.objects.filter(pago_id=pago_consulta.id)
            .select_related("pago__solicitud")
            .defer("pago__referencia_documental", "pago__huella_idempotencia")
            .first()
        )
        if evento_pago is not None:
            cronologia.append(evento_pago.como_historial())
    proyeccion_documental = proyectar_documentos(actor, solicitud)
    if proyeccion_documental is not None:
        cronologia.extend(proyeccion_documental.eventos)
    cronologia.sort(
        key=lambda evento: (
            evento.fecha_hora is None,
            evento.fecha_hora,
            evento.evento_id,
        )
    )

    acciones_decision = {
        act
        for act in ("aceptar", "postergar", "rechazar")
        if can_decide_expense(actor, solicitud, act)
    }
    can_decide = bool(acciones_decision)
    decision_form = (
        DecisionGastoForm(initial={"version": solicitud.version}) if can_decide else None
    )
    # Acción de pago: requiere ambos permisos, estado aceptado y ausencia de pago.
    # El detalle no lista opciones; el formulario de pago comprueba el respaldo
    # habilitado y explica el bloqueo y el camino según permisos.
    mostrar_estado_registro_pago = (
        pago_consulta is None
        and solicitud.estado == EstadoSolicitud.ACEPTADA
    )
    pago_permiso_registrar = (
        mostrar_estado_registro_pago
        and has_capability(actor, "gastos.registrar_pago")
    )
    pago_permiso_metadatos = (
        mostrar_estado_registro_pago
        and has_capability(actor, "documentos.ver_metadatos")
    )
    pago_permiso_incorporar = (
        mostrar_estado_registro_pago
        and has_capability(actor, "documentos.incorporar")
    )
    pago_permiso_consulta_global = (
        mostrar_estado_registro_pago
        and has_capability(actor, "gastos.consultar_todas")
    )
    puede_registrar_pago = (
        mostrar_estado_registro_pago
        and pago_permiso_registrar
        and pago_permiso_metadatos
        and pago_permiso_incorporar
        and pago_permiso_consulta_global
    )
    pago_provider_configurado = (
        cargar_proveedor_documental() is not None if puede_registrar_pago else False
    )
    pago_sin_respaldo_confirmado = False
    if puede_registrar_pago and pago_provider_configurado:
        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is not None:
            _, opciones_pago = carga
            pago_sin_respaldo_confirmado = len(opciones_pago) == 0

    respaldo_categoria = None
    if pago_consulta is not None and has_capability(actor, "documentos.consultar_metadatos"):
        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is not None:
            _, opciones = carga
            referencia_doc = (
                PagoExterno.objects.filter(solicitud=solicitud)
                .values_list("referencia_documental", flat=True)
                .first()
            )
            respaldo_categoria = derivar_categoria_respaldo(referencia_doc, opciones)

    revisiones_datos_transferencia = consultar_revisiones_datos_transferencia(
        actor, solicitud.pk
    )
    datos_transferencia_actual = (
        revisiones_datos_transferencia[-1] if revisiones_datos_transferencia else None
    )
    datos_transferencia_historial = (
        tuple(reversed(revisiones_datos_transferencia[:-1]))
        if revisiones_datos_transferencia
        else ()
    )
    pago_registrado = pago_consulta is not None
    puede_editar_datos = (
        revisiones_datos_transferencia is not None
        and puede_editar_datos_transferencia(
            actor, solicitud, pago_registrado=pago_registrado
        )
    )

    factura_vigente = None
    if proyeccion_documental is not None:
        for version in proyeccion_documental.versiones:
            if version.vigente and version.tipo == Documento.Tipo.FACTURA_PROVEEDOR:
                factura_vigente = version
                break

    def importe_ars(valor: Decimal | None) -> str:
        if valor is None:
            return "—"
        return "$ " + f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))

    solicitante = solicitud.solicitante
    detalle_es_solicitante = actor.subject_id == solicitud.solicitante_id
    detalle_actor_registra_pago = has_capability(actor, "gastos.registrar_pago")
    detalle_solicitante = {
        "nombre": solicitante.get_full_name().strip() or solicitante.get_username(),
        "correo": (
            solicitante.email
            if detalle_es_solicitante
            or can_decide
            or detalle_actor_registra_pago
            else ""
        ),
    }
    detalle_respaldos_titular = (
        proyectar_respaldos_titular(actor, solicitud)
        if detalle_es_solicitante
        else None
    )
    tiene_respaldo_titular_observado_o_rechazado = any(
        respaldo.resultado in ("OBSERVADO", "RECHAZADO")
        for respaldo in (detalle_respaldos_titular or ())
    )
    tiene_respaldo_titular_para_corregir = any(
        respaldo.resultado in ("OBSERVADO", "RECHAZADO")
        and respaldo.puede_reemplazar
        for respaldo in (detalle_respaldos_titular or ())
    )
    versiones_vigentes = (
        tuple(v for v in proyeccion_documental.versiones if v.vigente)
        if proyeccion_documental is not None
        else ()
    )
    if proyeccion_documental is not None:
        sin_revision = [v for v in versiones_vigentes if v.revision_actual is None]
        con_revision = [v for v in versiones_vigentes if v.revision_actual is not None]
        sin_revision.sort(
            key=lambda v: (v.fecha_incorporacion, v.documento_id),
            reverse=True,
        )
        con_revision.sort(
            key=lambda v: (v.fecha_incorporacion, v.documento_id),
            reverse=True,
        )
        detalle_versiones_actuales = tuple(sin_revision + con_revision)
    else:
        detalle_versiones_actuales = ()
    tiene_revision_pendiente_u_observada = any(
        v.revision_actual is None
        or v.revision_actual.resultado == "OBSERVADO"
        or "observ" in v.revision_actual.resultado_mostrado.lower()
        for v in versiones_vigentes
    )
    tiene_revision_rechazada = any(
        v.revision_actual is not None
        and (
            v.revision_actual.resultado == "RECHAZADO"
            or "rechaz" in v.revision_actual.resultado_mostrado.lower()
        )
        for v in versiones_vigentes
    )
    detalle_pendientes = []
    if solicitud.estado == EstadoSolicitud.ACEPTADA:
        if pago_consulta is None:
            detalle_pendientes.append(("Sin pago registrado", "#pago-externo"))
        if pago_sin_respaldo_confirmado:
            detalle_pendientes.append(("Falta respaldo comercial", "#respaldo-documental"))
        if (
            pago_consulta
            and pago_consulta.constancia_atp_pendiente
            and not detalle_es_solicitante
        ):
            detalle_pendientes.append(("Constancia ATP pendiente", "#pago-externo"))
        if respaldo_categoria == "presupuesto" and proyeccion_documental is not None:
            if factura_vigente is None:
                detalle_pendientes.append(("Falta factura definitiva", "#seguimiento-factura"))
            elif factura_vigente.revision_actual is None:
                detalle_pendientes.append(("Factura en revisión", "#seguimiento-factura"))
    if detalle_es_solicitante and tiene_respaldo_titular_para_corregir:
        detalle_pendientes.append(
            ("Respaldo observado o rechazado para corregir", "#respaldo-documental")
        )
    elif detalle_es_solicitante and tiene_respaldo_titular_observado_o_rechazado:
        detalle_pendientes.append(
            ("Respaldo observado o rechazado", "#respaldo-documental")
        )
    elif proyeccion_documental is not None and (
        tiene_revision_pendiente_u_observada or tiene_revision_rechazada
    ):
        detalle_pendientes.append(("Revisión documental pendiente", "#respaldo-documental"))

    evidencia_documental_suficiente = (
        (
            respaldo_categoria == "factura"
            and any(
                v.tipo in (Documento.Tipo.FACTURA_PROVEEDOR, Documento.Tipo.TICKET_NO_FISCAL)
                and v.revision_actual is not None
                and v.revision_actual.resultado == "ACEPTADO"
                for v in versiones_vigentes
            )
        )
        or (
            respaldo_categoria == "presupuesto"
            and factura_vigente is not None
            and factura_vigente.revision_actual is not None
            and factura_vigente.revision_actual.resultado == "ACEPTADO"
        )
    )
    detalle_al_dia = bool(
        solicitud.estado == EstadoSolicitud.ACEPTADA
        and pago_consulta is not None
        and pago_consulta.tiene_comprobante_bancario
        and not pago_consulta.es_registro_legado
        and not pago_consulta.constancia_atp_pendiente
        and proyeccion_documental is not None
        and len(versiones_vigentes) > 0
        and not tiene_revision_pendiente_u_observada
        and not tiene_revision_rechazada
        and evidencia_documental_suficiente
        and len(detalle_pendientes) == 0
    )

    respaldo_cerrado = solicitud.estado == EstadoSolicitud.RECHAZADA
    puede_incorporar_documentos = not respaldo_cerrado and has_capability(
        actor, "documentos.incorporar"
    )
    if puede_incorporar_documentos:
        if detalle_aporte_form is None or detalle_aporte_versiones is None:
            form_aporte, vers_aporte = _formulario_aporte_documental(
                actor,
                solicitud,
                preseleccionar_reemplaza_id=preseleccionar_reemplaza_id,
            )
            if detalle_aporte_form is None:
                detalle_aporte_form = form_aporte
            if detalle_aporte_versiones is None:
                detalle_aporte_versiones = vers_aporte
    else:
        detalle_aporte_form = None
        detalle_aporte_versiones = None
        detalle_aporte_con_error = False

    if detalle_datos_transferencia_form is None and puede_editar_datos:
        detalle_datos_transferencia_form = DatosTransferenciaForm(
            initial=(
                datos_de_revision(datos_transferencia_actual)
                if datos_transferencia_actual is not None
                else {}
            )
        )

    return {
        "solicitud": solicitud,
        "detalle_solicitante": detalle_solicitante,
        "detalle_es_solicitante": detalle_es_solicitante,
        "detalle_actor_registra_pago": detalle_actor_registra_pago,
        "detalle_al_dia": detalle_al_dia,
        "detalle_importes": {
            "estimado": importe_ars(solicitud.monto_estimado),
            "bruto": importe_ars(pago_consulta.monto_bruto if pago_consulta else None),
            "retencion": importe_ars(pago_consulta.monto_retencion_atp if pago_consulta else None),
            "neto": importe_ars(pago_consulta.importe if pago_consulta else None),
        },
        "detalle_pendientes": [
            {"texto": texto, "ancla": ancla} for texto, ancla in detalle_pendientes
        ],
        "detalle_puede_revisar": has_capability(actor, "documentos.revisar"),
        "actor": actor,
        "tramite_id": f"gastos:{solicitud.pk}",
        "decisiones": decisiones,
        "ultima_decision": decisiones[-1] if decisiones else None,
        "pago_consulta": pago_consulta,
        "cronologia": cronologia,
        "can_decide": can_decide,
        "acciones_decision": acciones_decision,
        "decision_form": decision_form,
        "mostrar_estado_registro_pago": mostrar_estado_registro_pago,
        "puede_registrar_pago": puede_registrar_pago,
        "pago_permiso_registrar": pago_permiso_registrar,
        "pago_permiso_metadatos": pago_permiso_metadatos,
        "pago_permiso_incorporar": pago_permiso_incorporar,
        "pago_permiso_consulta_global": pago_permiso_consulta_global,
        "pago_provider_configurado": pago_provider_configurado,
        "pago_sin_respaldo_confirmado": pago_sin_respaldo_confirmado,
        "puede_rectificar_pago": (
            pago_consulta is not None
            and has_capability(actor, "gastos.registrar_pago")
        ),
        "puede_incorporar_atp": (
            pago_consulta is not None
            and pago_consulta.constancia_atp_pendiente
            and has_capability(actor, "gastos.registrar_pago")
            and has_capability(actor, "documentos.incorporar")
            and has_capability(actor, "gastos.consultar_todas")
        ),
        "puede_descargar_documentos": has_capability(
            actor, "documentos.recuperar_contenido"
        ),
        "cambios_pago": (
            consultar_cambios_pago(actor, solicitud.pk) if pago_consulta else ()
        ),
        "respaldo_categoria": respaldo_categoria,
        "datos_transferencia": revisiones_datos_transferencia,
        "datos_transferencia_autorizado": revisiones_datos_transferencia is not None,
        "datos_transferencia_actual": datos_transferencia_actual,
        "datos_transferencia_historial": datos_transferencia_historial,
        "puede_editar_datos_transferencia": puede_editar_datos,
        "detalle_datos_transferencia_form": detalle_datos_transferencia_form,
        "detalle_datos_transferencia_con_error": bool(
            detalle_datos_transferencia_con_error
        ),
        "mostrar_seguimiento_factura": (
            pago_consulta is not None and proyeccion_documental is not None
        ),
        "factura_vigente": factura_vigente,
        "puede_incorporar_documentos": puede_incorporar_documentos,
        "respaldo_cerrado": respaldo_cerrado,
        "detalle_aporte_form": detalle_aporte_form,
        "detalle_aporte_versiones": detalle_aporte_versiones,
        "detalle_aporte_con_error": bool(detalle_aporte_con_error),
        "detalle_respaldos_titular": detalle_respaldos_titular,
        "preseleccionar_reemplaza_id": preseleccionar_reemplaza_id,
        "puede_ver_documentos": proyeccion_documental is not None,
        "versiones_documentales": (
            proyeccion_documental.versiones
            if proyeccion_documental is not None
            else None
        ),
        "detalle_versiones_actuales": detalle_versiones_actuales,
    }


class SolicitudGastoDetailView(View):
    """Detalle de una solicitud de gasto visible para el actor."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        # Aislamiento estricto: 404 para inexistentes o ajenas no visibles
        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        reemplaza_param = request.GET.get("reemplaza")
        return render(
            request,
            "gastos/solicitud_detail.html",
            _solicitud_detail_context(
                actor,
                solicitud,
                preseleccionar_reemplaza_id=reemplaza_param,
            ),
        )


class SolicitudGastoDatosTransferenciaView(View):
    """Agrega o corrige los datos de transferencia del titular.

    La ruta exige visibilidad del gasto, titularidad y ``gastos.presentar``. El
    servicio revalida y serializa la escritura con el pago sobre la misma fila
    del gasto. Una pantalla bloqueada no ofrece el formulario; un POST bloqueado
    conserva lo ingresado y responde 409 sin escribir.
    """

    template_name = "gastos/datos_transferencia_form.html"

    def _solicitud_autorizada(
        self, request: HttpRequest, pk: int
    ) -> tuple[Any, Any]:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result, None
        actor = result
        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        if (
            solicitud.solicitante_id != actor.subject_id
            or not has_capability(actor, "gastos.presentar")
        ):
            raise PermissionDenied(
                "Sólo el titular con capacidad para presentar gastos puede "
                "informar estos datos."
            )
        return actor, solicitud

    @staticmethod
    def _contexto(
        actor: Any,
        solicitud: Any,
        form: DatosTransferenciaForm,
    ) -> dict[str, Any]:
        revisiones = (
            consultar_revisiones_datos_transferencia(actor, solicitud.pk) or ()
        )
        return {
            "actor": actor,
            "solicitud": solicitud,
            "form": form,
            "revision_actual": revisiones[-1] if revisiones else None,
            "historial_datos": (
                tuple(reversed(revisiones[:-1])) if revisiones else ()
            ),
        }

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        result, solicitud = self._solicitud_autorizada(request, pk)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        pago_registrado = _pago_externo_registrado(solicitud)
        if not puede_editar_datos_transferencia(
            actor,
            solicitud,
            pago_registrado=pago_registrado,
        ):
            if pago_registrado:
                messages.info(
                    request,
                    "La solicitud ya tiene un pago registrado; en esta demo los "
                    "datos de transferencia no se corrigen después del pago.",
                )
            elif solicitud.estado == EstadoSolicitud.RECHAZADA:
                messages.info(
                    request,
                    "La solicitud fue rechazada y no admite nuevos datos de "
                    "transferencia.",
                )
            else:
                raise PermissionDenied(
                    "No podés modificar los datos de transferencia de este gasto."
                )
            return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

        revisiones = (
            consultar_revisiones_datos_transferencia(actor, solicitud.pk) or ()
        )
        actual = revisiones[-1] if revisiones else None
        form = DatosTransferenciaForm(
            initial=datos_de_revision(actual) if actual is not None else {}
        )
        return render(
            request,
            self.template_name,
            self._contexto(actor, solicitud, form),
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result, solicitud = self._solicitud_autorizada(request, pk)
        if isinstance(result, HttpResponse):
            return result
        actor = result
        es_detalle = (request.POST.get("origen_transferencia") or "").strip() == "detalle"

        centro_costo_default = ""
        if es_detalle and not request.POST.get("centro_costo", "").strip():
            centro_costo_default = centro_costo_transferencia_por_defecto(solicitud)
        form = DatosTransferenciaForm(request.POST, centro_costo_default=centro_costo_default)
        status = 400
        if form.is_valid():
            try:
                revision = registrar_revision_datos_transferencia(
                    actor=actor,
                    solicitud_id=solicitud.pk,
                    datos=form.datos_transferencia,
                )
            except DatosTransferenciaNotFoundError as exc:
                raise Http404("Solicitud inexistente o no visible.") from exc
            except DatosTransferenciaPermissionDeniedError as exc:
                raise PermissionDenied(str(exc)) from exc
            except DatosTransferenciaBloqueadaError as exc:
                form.add_error(None, str(exc))
                status = 409
            except DatosTransferenciaInvalidInputError as exc:
                form.add_error(None, str(exc))
                status = 400
            else:
                messages.success(
                    request,
                    f"Datos de transferencia guardados como revisión "
                    f"{revision.numero_revision}. No modifican el pago ni el "
                    "estado de la solicitud.",
                )
                return redirect(
                    reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
                )

        if es_detalle:
            context = _solicitud_detail_context(
                actor,
                solicitud,
                detalle_datos_transferencia_form=form,
                detalle_datos_transferencia_con_error=True,
            )
            return render(
                request,
                "gastos/solicitud_detail.html",
                context,
                status=status,
            )

        return render(
            request,
            self.template_name,
            self._contexto(actor, solicitud, form),
            status=status,
        )


class SolicitudGastoDocumentosView(View):
    """Aporta o reemplaza respaldo usando el servicio documental existente."""

    def _solicitud_autorizada(self, request: HttpRequest, pk: int) -> tuple[Any, Any]:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result, None
        actor = result
        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        if not has_capability(actor, "documentos.incorporar"):
            raise PermissionDenied("No tenés permiso para incorporar documentos.")
        if solicitud.estado == EstadoSolicitud.RECHAZADA:
            destino = reverse("gastos:detalle", kwargs={"pk": pk}) + "#respaldo-documental"
            return redirect(destino), None
        return actor, solicitud

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        result, solicitud = self._solicitud_autorizada(request, pk)
        if isinstance(result, HttpResponse):
            return result
        reemplaza_param = request.GET.get("reemplaza")
        form, versiones = _formulario_aporte_documental(
            result, solicitud, preseleccionar_reemplaza_id=reemplaza_param
        )
        return render(
            request,
            "gastos/documento_form.html",
            _contexto_formulario_aporte(result, solicitud, form, versiones),
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result, solicitud = self._solicitud_autorizada(request, pk)
        if isinstance(result, HttpResponse):
            return result
        actor = result
        es_detalle = (request.POST.get("origen_aporte") or "").strip() == "detalle"
        form, versiones = _formulario_aporte_documental(
            actor, solicitud, data=request.POST, files=request.FILES
        )
        status = 400
        if form.is_valid():
            reemplaza_id = form.cleaned_data["reemplaza_id"]
            if reemplaza_id and not any(
                str(v.documento_id) == str(reemplaza_id) for v in versiones
            ):
                form.add_error(
                    "reemplaza_id",
                    "Seleccione una versión vigente de este gasto o incorpore un documento nuevo.",
                )
            else:
                try:
                    incorporar(
                        actor=actor,
                        referencia=f"gastos:{solicitud.pk}",
                        archivo=form.cleaned_data["archivo"],
                        tipo=form.cleaned_data["tipo"],
                        procedencia=form.cleaned_data["procedencia"],
                        reemplaza_id=int(reemplaza_id) if reemplaza_id else None,
                    )
                except DocumentoNoVisible as exc:
                    raise Http404("La versión no está disponible para este gasto.") from exc
                except ArchivoInvalido as exc:
                    form.add_error(None, str(exc))
                except AlmacenamientoNoDisponible:
                    form.add_error(
                        None,
                        "No se pudo guardar el archivo; el documento no quedó incorporado.",
                    )
                    status = 503
                else:
                    messages.success(
                        request,
                        "El documento se incorporó. Su revisión se mantiene separada del aporte.",
                    )
                    if es_detalle:
                        return redirect(
                            reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
                            + "#respaldo-documental"
                        )
                    return redirect("gastos:detalle", pk=solicitud.pk)

        if es_detalle:
            context = _solicitud_detail_context(
                actor,
                solicitud,
                detalle_aporte_form=form,
                detalle_aporte_versiones=versiones,
                detalle_aporte_con_error=True,
            )
            return render(
                request,
                "gastos/solicitud_detail.html",
                context,
                status=status,
            )

        return render(
            request,
            "gastos/documento_form.html",
            _contexto_formulario_aporte(actor, solicitud, form, versiones),
            status=status,
        )


class SolicitudGastoDecidirView(View):
    """Registro de la decisión humana autorizada sobre una solicitud."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        action = request.POST.get("action")
        version = request.POST.get("version")
        motivo = request.POST.get("motivo")

        try:
            decide_expense(
                actor=actor,
                solicitud_id=pk,
                action=action,
                expected_version=version,
                motivo=motivo,
            )
            return redirect(reverse("gastos:detalle", kwargs={"pk": pk}))
        except ExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except ExpensePermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except InvalidDecisionInputError as exc:
            solicitud = visible_expenses(actor).filter(pk=pk).first()
            if solicitud:
                msg = str(exc)
                es_error_motivo = "motivo" in msg.lower()
                form = DecisionGastoForm(data=request.POST)
                form.is_valid()
                form.add_error("motivo" if es_error_motivo else None, msg)
                context = _solicitud_detail_context(actor, solicitud)
                context.update(
                    {
                        "decision_form": form,
                        "error_decision": None if es_error_motivo else msg,
                    }
                )
                return render(
                    request,
                    "gastos/solicitud_detail.html",
                    context,
                    status=400,
                )
            return HttpResponse(str(exc), status=400)
        except (ConcurrencyConflictError, InvalidTransitionError):
            solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
            context = _solicitud_detail_context(actor, solicitud)
            context["error_decision"] = (
                "No se registró la decisión. Revisá el estado actual de la solicitud "
                "y las acciones disponibles."
            )
            return render(request, "gastos/solicitud_detail.html", context, status=409)

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return HttpResponseNotAllowed(["POST"])


class SolicitudGastoPagoView(View):
    """Formulario y registro documentado del pago externo de una solicitud aceptada.

    Orden de comprobaciones:
    1. Identidad de sesión y visibilidad del gasto (404 antes de permisos).
    2. ``gastos.registrar_pago`` (403).
    3. Para un alta nueva, además ``documentos.ver_metadatos`` (listado C01),
       ``documentos.incorporar`` y ``gastos.consultar_todas`` (clasificación
       documental vigente). No se concede ninguna capacidad por abrir el formulario.
    4. Un reenvío sobre un pago existente sólo reautoriza el registro de pago y
       se resuelve contra la representación original del alta, sin C01 ni proveedor.
    5. La carga de archivos la orquesta el servicio con ``operacion_documental``.
    """

    template_name = "gastos/pago_form.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PermissionDenied("No posee capacidad para registrar pagos.")

        if _pago_externo_registrado(solicitud) or solicitud.estado != EstadoSolicitud.ACEPTADA:
            return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

        if not has_capability(actor, "documentos.ver_metadatos"):
            raise PermissionDenied(
                "No posee capacidad para consultar metadatos documentales."
            )
        formulario_habilitado = has_capability(
            actor, "documentos.incorporar"
        ) and has_capability(actor, "gastos.consultar_todas")
        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is None:
            return _servicio_pago_no_disponible()
        _, opciones = carga

        monto_estimado = solicitud.monto_estimado or Decimal("0.00")
        form = PagoExternoForm(
            opciones_documentales=opciones,
            initial={
                "monto_bruto": self._fmt_ar(monto_estimado),
                "monto_retencion_atp": "0,00",
                "atp_decision": "ahora",
            },
        )
        return render(
            request,
            self.template_name,
            self._contexto_pago(
                actor,
                solicitud,
                form,
                opciones,
                formulario_habilitado=formulario_habilitado,
            ),
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PermissionDenied("No posee capacidad para registrar pagos.")

        # Reenvío sobre un pago ya persistido: idempotencia contra el alta original.
        if _pago_externo_registrado(solicitud):
            return self._reenviar_pago_existente(request, actor, solicitud)

        if solicitud.estado != EstadoSolicitud.ACEPTADA:
            form = PagoExternoForm(request.POST, request.FILES, opciones_documentales=[])
            form.add_error(
                None,
                "La solicitud ya no está en un estado que permita registrar un pago.",
            )
            return render(
                request,
                self.template_name,
                self._contexto_pago(
                    actor,
                    solicitud,
                    form,
                    [],
                    formulario_habilitado=False,
                ),
                status=409,
            )

        self._exigir_capacidades_documentales(actor)

        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is None:
            reenvio = self._reenviar_si_aparecio_pago(request, actor, solicitud)
            if reenvio is not None:
                return reenvio
            return _servicio_pago_no_disponible()
        proveedor, opciones = carga

        form = PagoExternoForm(
            request.POST, request.FILES, opciones_documentales=opciones
        )
        if not form.is_valid():
            reenvio = self._reenviar_si_aparecio_pago(request, actor, solicitud)
            if reenvio is not None:
                return reenvio
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=400,
            )

        reenvio = self._reenviar_si_aparecio_pago(request, actor, solicitud)
        if reenvio is not None:
            return reenvio

        atp_despues = form.cleaned_data.get("atp_decision") == "despues"
        try:
            registrar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                monto_bruto=form.cleaned_data["monto_bruto"],
                monto_retencion_atp=form.cleaned_data["monto_retencion_atp"],
                fecha_pago=form.cleaned_data["fecha_pago"],
                referencia_externa=form.cleaned_data["referencia_externa"],
                referencia_documental=form.cleaned_data["referencia_documental"],
                referencia_atp=form.cleaned_data["referencia_atp"],
                comprobante_bancario=form.cleaned_data.get("comprobante_bancario"),
                constancia_atp=form.cleaned_data.get("constancia_atp"),
                incorporar_atp_despues=atp_despues,
                document_provider=proveedor,
            )
        except PaymentExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except PaymentPermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except PaymentInvalidInputError as exc:
            msg = str(exc)
            form.add_error(None, msg)
            if "retención debe ser menor" in msg.lower():
                form.add_error("monto_retencion_atp", msg)
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=400,
            )
        except PaymentInvalidExpenseStateError:
            form.add_error(
                None,
                "La solicitud ya no está en un estado que permita registrar un pago.",
            )
            return render(
                request,
                self.template_name,
                self._contexto_pago(
                    actor,
                    solicitud,
                    form,
                    opciones,
                    formulario_habilitado=False,
                ),
                status=409,
            )
        except PaymentConflictError as exc:
            return HttpResponse(str(exc), status=409)
        except DocumentVerificationError:
            opciones_actualizadas = _listar_opciones_documentales(
                proveedor, actor, solicitud
            )
            if opciones_actualizadas is not None:
                opciones = opciones_actualizadas
                form = PagoExternoForm(
                    request.POST,
                    request.FILES,
                    opciones_documentales=opciones_actualizadas,
                )
            form.add_error(None, "No se pudo verificar el respaldo documental del pago.")
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=409,
            )
        except AlmacenamientoNoDisponible:
            form.add_error(
                None,
                "No se pudo guardar la documentación del pago; no quedó registrado. "
                "Volvé a elegir el archivo.",
            )
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=503,
            )
        except OSError:
            form.add_error(
                None,
                "No se pudo guardar la documentación del pago; no quedó registrado. "
                "Volvé a elegir el archivo.",
            )
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=503,
            )

        messages.success(
            request,
            "Pago externo registrado. El comprobante bancario queda disponible "
            "según tus permisos documentales.",
        )
        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

    @staticmethod
    def _exigir_capacidades_documentales(actor: Any) -> None:
        if not has_capability(actor, "documentos.ver_metadatos"):
            raise PermissionDenied(
                "No posee capacidad para consultar metadatos documentales."
            )
        if not has_capability(actor, "documentos.incorporar"):
            raise PermissionDenied("No posee capacidad para incorporar documentos.")
        if not has_capability(actor, "gastos.consultar_todas"):
            raise PermissionDenied(
                "La incorporación del comprobante exige consulta global de gastos."
            )

    def _reenviar_pago_existente(
        self, request: HttpRequest, actor: Any, solicitud: Any
    ) -> HttpResponse:
        """Resuelve un reenvío de alta sin proveedor ni C01.

        La comparación autoritativa usa la representación original del alta. Un
        reenvío idéntico redirige sin escribir documentos ni eventos; datos
        distintos responden 409. No se exige volver a adjuntar el PDF ni elegir
        la constancia ATP para reconocer una respuesta perdida.
        """
        try:
            registrar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                importe=request.POST.get("importe") or None,
                monto_bruto=request.POST.get("monto_bruto") or None,
                monto_retencion_atp=(
                    request.POST.get("monto_retencion_atp") or Decimal("0.00")
                ),
                fecha_pago=request.POST.get("fecha_pago"),
                referencia_externa=request.POST.get("referencia_externa", ""),
                referencia_documental=request.POST.get("referencia_documental"),
                referencia_atp=request.POST.get("referencia_atp", ""),
                incorporar_atp_despues=True,
                document_provider=None,
            )
        except PaymentExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except PaymentPermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except PaymentInvalidInputError as exc:
            context = _solicitud_detail_context(actor, solicitud)
            context["error_pago"] = str(exc)
            return render(
                request,
                "gastos/solicitud_detail.html",
                context,
                status=400,
            )
        except (PaymentInvalidExpenseStateError, PaymentConflictError) as exc:
            return HttpResponse(str(exc), status=409)
        except DocumentVerificationError:
            return HttpResponse(
                "No se pudo verificar el respaldo documental del pago.",
                status=409,
            )
        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

    def _reenviar_si_aparecio_pago(
        self, request: HttpRequest, actor: Any, solicitud: Any
    ) -> HttpResponse | None:
        """Reconoce un pago confirmado durante la ventana de una salida preliminar."""
        if not _pago_externo_registrado(solicitud):
            return None
        return self._reenviar_pago_existente(request, actor, solicitud)

    @staticmethod
    def _fmt_ar(dec: Decimal | None) -> str:
        if dec is None:
            return "—"
        partes = f"{dec:.2f}".split(".")
        entero = f"{int(partes[0]):,}".replace(",", ".")
        return f"{entero},{partes[1]}"

    @staticmethod
    def _contexto_pago(
        actor: Any,
        solicitud: Any,
        form: PagoExternoForm,
        opciones: list[OpcionDocumental],
        *,
        formulario_habilitado: bool = True,
    ) -> dict[str, Any]:
        base_imponible = obtener_base_imponible_atp()
        aplica_atp = (
            solicitud.monto_estimado is not None
            and solicitud.monto_estimado >= base_imponible
        )
        revisiones = consultar_revisiones_datos_transferencia(actor, solicitud.pk) or ()
        datos_actuales = revisiones[-1] if revisiones else None

        solicitante_usuario = getattr(solicitud, "solicitante", None)
        solicitante_nombre = ""
        solicitante_email = ""
        if solicitante_usuario is not None:
            if hasattr(solicitante_usuario, "get_full_name"):
                solicitante_nombre = solicitante_usuario.get_full_name().strip()
            if not solicitante_nombre:
                solicitante_nombre = getattr(solicitante_usuario, "username", "")
            solicitante_email = getattr(solicitante_usuario, "email", "") or ""
        solicitante_display = solicitante_nombre or "Solicitante no informado"

        def _decimal_formulario(valor: Any) -> Decimal | None:
            if valor in (None, ""):
                return None
            texto = str(valor).strip()
            if texto.startswith("$"):
                texto = texto[1:].strip()
            if "." in texto and "," in texto:
                pos_punto = texto.rfind(".")
                pos_coma = texto.rfind(",")
                if pos_coma > pos_punto:
                    texto = texto.replace(".", "").replace(",", ".")
                else:
                    texto = texto.replace(",", "")
            elif "," in texto:
                texto = texto.replace(",", ".")
            elif texto.count(".") > 1:
                texto = texto.replace(".", "")
            try:
                return Decimal(texto)
            except Exception:
                return None

        bruto_valor = _decimal_formulario(form["monto_bruto"].value())
        if bruto_valor is None:
            bruto_valor = solicitud.monto_estimado
        retencion_raw = form["monto_retencion_atp"].value()
        if form.is_bound and retencion_raw in (None, ""):
            retencion_valor = None
        else:
            retencion_valor = _decimal_formulario(retencion_raw)
            if retencion_valor is None and not form.is_bound:
                retencion_valor = Decimal("0.00")
        neto_inicial = (
            bruto_valor - retencion_valor
            if bruto_valor is not None
            and retencion_valor is not None
            and bruto_valor > retencion_valor
            else None
        )
        if retencion_valor is None:
            resumen_atp = "Por definir"
            mostrar_atp = False
        elif retencion_valor == Decimal("0.00"):
            resumen_atp = "No aplica"
            mostrar_atp = False
        else:
            mostrar_atp = True
            if form.files.get("constancia_atp") is not None:
                resumen_atp = "Adjunta"
            elif form["atp_decision"].value() == "despues":
                resumen_atp = "Pendiente de aporte"
            else:
                resumen_atp = "Pendiente de adjuntar"

        respaldo_seleccionado_etiqueta = ""
        if opciones:
            valor_sel = form["referencia_documental"].value()
            opcion_sel = next(
                (o for o in opciones if o.referencia_documental == valor_sel),
                None,
            )
            if opcion_sel is None and opciones:
                opcion_sel = opciones[0]
            if opcion_sel is not None:
                respaldo_seleccionado_etiqueta = PagoExternoForm._etiqueta_opcion(opcion_sel)

        max_bytes = getattr(settings, "DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)
        return {
            "solicitud": solicitud,
            "solicitante_nombre": solicitante_display,
            "solicitante_email": solicitante_email,
            "actor": actor,
            "form": form,
            "opciones_documentales": opciones,
            "respaldo_seleccionado_etiqueta": respaldo_seleccionado_etiqueta,
            "formulario_habilitado": formulario_habilitado,
            "puede_incorporar_documentos": has_capability(
                actor, "documentos.incorporar"
            ),
            "tramite_id": f"gastos:{solicitud.pk}",
            "base_imponible_atp": base_imponible,
            "base_imponible_atp_formateada": SolicitudGastoPagoView._fmt_ar(base_imponible),
            "aplica_atp": aplica_atp,
            "max_upload_bytes": max_bytes,
            "max_upload_mib": max(1, int(max_bytes / (1024 * 1024))),
            "bruto_inicial": SolicitudGastoPagoView._fmt_ar(bruto_valor),
            "retencion_inicial": (
                SolicitudGastoPagoView._fmt_ar(retencion_valor)
                if retencion_valor is not None
                else "—"
            ),
            "neto_inicial": (
                SolicitudGastoPagoView._fmt_ar(neto_inicial)
                if neto_inicial is not None
                else "—"
            ),
            "monto_estimado_formateado": SolicitudGastoPagoView._fmt_ar(
                solicitud.monto_estimado
            ),
            "mostrar_atp_inicial": mostrar_atp,
            "resumen_atp_inicial": resumen_atp,
            "datos_transferencia_actual": datos_actuales,
            "beneficiario": (
                datos_actuales.titular_nombre if datos_actuales is not None else ""
            ),
            "puede_ver_datos_banco": datos_actuales is not None,
        }


class SolicitudGastoPagoRectificarView(View):
    """Rectificación autorizada de datos y comprobante, con versión esperada."""

    template_name = "gastos/pago_rectificacion.html"

    def _solicitud_autorizada(
        self, request: HttpRequest, pk: int
    ) -> tuple[Any, Any, Any]:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result, None, None
        actor = result
        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PermissionDenied("No posee capacidad para rectificar pagos.")
        pago = PagoExterno.objects.filter(solicitud=solicitud).first()
        if pago is None:
            raise Http404("La solicitud no tiene un pago registrado.")
        return actor, solicitud, pago

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor, solicitud, pago = self._solicitud_autorizada(request, pk)
        if isinstance(actor, HttpResponse):
            return actor
        return render(
            request,
            self.template_name,
            self._contexto(actor, solicitud, pago, self._formulario(pago)),
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor, solicitud, pago = self._solicitud_autorizada(request, pk)
        if isinstance(actor, HttpResponse):
            return actor
        form = RectificacionPagoForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=400,
            )
        try:
            pago = rectificar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                version_esperada=form.cleaned_data["version_esperada"],
                motivo=form.cleaned_data["motivo"],
                fecha_pago=form.cleaned_data["fecha_pago"],
                monto_bruto=form.cleaned_data["monto_bruto"],
                monto_retencion_atp=form.cleaned_data["monto_retencion_atp"],
                referencia_externa=form.cleaned_data["referencia_externa"],
                referencia_atp=form.cleaned_data["referencia_atp"],
                comprobante_bancario=form.cleaned_data.get("comprobante_bancario"),
            )
        except PaymentExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except PaymentPermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except PaymentVersionConflictError as exc:
            form.add_error(None, str(exc))
            pago.refresh_from_db()
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=409,
            )
        except PaymentConflictError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=409,
            )
        except PaymentInvalidInputError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=400,
            )
        except AlmacenamientoNoDisponible:
            form.add_error(
                None,
                "No se pudo guardar el comprobante; el pago conserva su versión anterior. "
                "Volvé a elegir el archivo.",
            )
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=503,
            )
        except OSError:
            form.add_error(
                None,
                "No se pudo guardar el comprobante; el pago conserva su versión anterior. "
                "Volvé a elegir el archivo.",
            )
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=503,
            )
        messages.success(
            request,
            f"Pago rectificado a la versión {pago.version}. La historia anterior "
            "se conserva.",
        )
        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

    @staticmethod
    def _formulario(pago: PagoExterno) -> RectificacionPagoForm:
        return RectificacionPagoForm(
            initial={
                "version_esperada": pago.version,
                "fecha_pago": pago.fecha_pago.isoformat(),
                "monto_bruto": f"{pago.monto_bruto:.2f}",
                "monto_retencion_atp": f"{pago.monto_retencion_atp:.2f}",
                "referencia_externa": pago.referencia_externa,
                "referencia_atp": pago.referencia_atp,
            }
        )

    @staticmethod
    def _contexto(
        actor: Any,
        solicitud: Any,
        pago: PagoExterno,
        form: RectificacionPagoForm,
    ) -> dict[str, Any]:
        revisiones = consultar_revisiones_datos_transferencia(actor, solicitud.pk) or ()
        return {
            "solicitud": solicitud,
            "pago": pago,
            "pago_consulta": consultar_pago_externo(actor, solicitud.pk),
            "form": form,
            "actor": actor,
            "datos_transferencia_actual": revisiones[-1] if revisiones else None,
            "cambios_pago": consultar_cambios_pago(actor, solicitud.pk),
            "puede_descargar_documentos": has_capability(
                actor, "documentos.recuperar_contenido"
            ),
            "tramite_id": f"gastos:{solicitud.pk}",
            "max_upload_bytes": getattr(
                settings, "DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024
            ),
            "max_upload_mib": max(
                1,
                int(
                    getattr(settings, "DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)
                    / (1024 * 1024)
                ),
            ),
        }


class SolicitudGastoPagoATPView(View):
    """Incorporación posterior de la constancia ATP pendiente."""

    template_name = "gastos/pago_atp_form.html"

    def _solicitud_autorizada(
        self, request: HttpRequest, pk: int
    ) -> tuple[Any, Any, Any]:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result, None, None
        actor = result
        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PermissionDenied("No posee capacidad para incorporar la constancia ATP.")
        pago = PagoExterno.objects.filter(solicitud=solicitud).first()
        if pago is None:
            raise Http404("La solicitud no tiene un pago registrado.")
        if pago.monto_retencion_atp <= Decimal("0.00") or pago.constancia_atp_id is not None:
            return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk})), None, None
        if not has_capability(actor, "documentos.incorporar") or not has_capability(
            actor, "gastos.consultar_todas"
        ):
            raise PermissionDenied(
                "No posee las capacidades documentales para incorporar la constancia ATP."
            )
        return actor, solicitud, pago

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor, solicitud, pago = self._solicitud_autorizada(request, pk)
        if isinstance(actor, HttpResponse):
            return actor
        form = ConstanciaATPForm(initial={"version_esperada": pago.version})
        return render(
            request,
            self.template_name,
            self._contexto(actor, solicitud, pago, form),
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor, solicitud, pago = self._solicitud_autorizada(request, pk)
        if isinstance(actor, HttpResponse):
            return actor
        form = ConstanciaATPForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=400,
            )
        try:
            pago = incorporar_constancia_atp_posterior(
                actor=actor,
                solicitud_id=solicitud.pk,
                version_esperada=form.cleaned_data["version_esperada"],
                motivo=form.cleaned_data["motivo"],
                constancia_atp=form.cleaned_data["constancia_atp"],
            )
        except PaymentExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except PaymentPermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except PaymentConflictError as exc:
            form.add_error(None, str(exc))
            pago.refresh_from_db()
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=409,
            )
        except PaymentInvalidInputError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=400,
            )
        except AlmacenamientoNoDisponible:
            form.add_error(
                None,
                "No se pudo guardar la constancia; el pago conserva su pendiente. "
                "Volvé a elegir el archivo.",
            )
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=503,
            )
        except OSError:
            form.add_error(
                None,
                "No se pudo guardar la constancia; el pago conserva su pendiente. "
                "Volvé a elegir el archivo.",
            )
            return render(
                request,
                self.template_name,
                self._contexto(actor, solicitud, pago, form),
                status=503,
            )
        messages.success(
            request,
            "Constancia ATP incorporada. El pendiente documental quedó resuelto; "
            "esto no cierra el trámite.",
        )
        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

    @staticmethod
    def _contexto(
        actor: Any,
        solicitud: Any,
        pago: PagoExterno,
        form: ConstanciaATPForm,
    ) -> dict[str, Any]:
        return {
            "solicitud": solicitud,
            "pago": pago,
            "form": form,
            "actor": actor,
            "tramite_id": f"gastos:{solicitud.pk}",
            "puede_descargar_documentos": has_capability(
                actor, "documentos.recuperar_contenido"
            ),
            "max_upload_bytes": getattr(
                settings, "DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024
            ),
            "max_upload_mib": max(
                1,
                int(
                    getattr(settings, "DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)
                    / (1024 * 1024)
                ),
            ),
        }


def _puede_administrar_catalogos(actor: Any) -> bool:
    """Verifica si el actor posee facultades para administrar catálogos y parámetros."""
    if actor is None:
        return False
    return has_capability(actor, "gastos.decidir") or has_capability(
        actor, "gastos.registrar_pago"
    )


CentroCostoEdicionForm = forms.modelform_factory(CentroCosto, fields=["nombre"])


class GestionCatalogosView(View):
    """Administración de catálogos (centros de costo) y parámetros de Cooperadora."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result
        if not _puede_administrar_catalogos(actor):
            raise PermissionDenied("No posee permisos para administrar catálogos y parámetros.")
        self.actor = actor
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest) -> HttpResponse:
        centros = CentroCosto.objects.all().order_by("nombre")
        centro_form = CentroCostoForm()
        atp_form = ParametrosATPForm(
            initial={
                "base_imponible_atp": obtener_base_imponible_atp(),
                "alicuota_atp": obtener_alicuota_atp(),
            }
        )
        return render(
            request,
            "gastos/gestion_catalogos.html",
            {
                "actor": self.actor,
                "centros_costo": centros,
                "centro_form": centro_form,
                "atp_form": atp_form,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        action = request.POST.get("action", "").strip()
        centros = CentroCosto.objects.all().order_by("nombre")

        if action == "crear_centro":
            centro_form = CentroCostoForm(request.POST)
            atp_form = ParametrosATPForm(
                initial={
                    "base_imponible_atp": obtener_base_imponible_atp(),
                    "alicuota_atp": obtener_alicuota_atp(),
                }
            )
            if centro_form.is_valid():
                centro_form.save()
                messages.success(
                    request,
                    f"Centro de costo '{centro_form.instance.nombre}' creado exitosamente.",
                )
                return redirect(reverse("gastos:gestion_catalogos"))
            return render(
                request,
                "gastos/gestion_catalogos.html",
                {
                    "actor": self.actor,
                    "centros_costo": centros,
                    "centro_form": centro_form,
                    "atp_form": atp_form,
                },
                status=400,
            )

        if action == "editar_centro":
            try:
                centro_id = int(request.POST.get("centro_id", ""))
            except ValueError as exc:
                raise Http404("Centro de costo no encontrado.") from exc
            centro = get_object_or_404(CentroCosto, pk=centro_id)
            edicion_form = CentroCostoEdicionForm(
                request.POST, instance=centro, auto_id=f"id_centro_{centro.pk}_%s"
            )
            if edicion_form.is_valid():
                centro.nombre = edicion_form.cleaned_data["nombre"]
                centro.save(update_fields=["nombre"])
                messages.success(request, "Nombre del centro de costo actualizado.")
                return redirect(reverse("gastos:gestion_catalogos"))
            return render(
                request,
                "gastos/gestion_catalogos.html",
                {
                    "actor": self.actor,
                    "centros_costo": centros,
                    "centro_form": CentroCostoForm(),
                    "atp_form": ParametrosATPForm(
                        initial={
                            "base_imponible_atp": obtener_base_imponible_atp(),
                            "alicuota_atp": obtener_alicuota_atp(),
                        }
                    ),
                    "centro_editado_id": centro.pk,
                    "centro_edicion_form": edicion_form,
                },
                status=400,
            )

        if action == "actualizar_atp":
            atp_form = ParametrosATPForm(request.POST)
            centro_form = CentroCostoForm()
            if atp_form.is_valid():
                actualizar_parametros_atp(
                    base_imponible=atp_form.cleaned_data["base_imponible_atp"],
                    alicuota=atp_form.cleaned_data["alicuota_atp"],
                    actor=self.actor,
                )
                messages.success(
                    request,
                    "Parámetros de retención ATP actualizados exitosamente.",
                )
                return redirect(reverse("gastos:gestion_catalogos"))
            return render(
                request,
                "gastos/gestion_catalogos.html",
                {
                    "actor": self.actor,
                    "centros_costo": centros,
                    "centro_form": centro_form,
                    "atp_form": atp_form,
                },
                status=400,
            )

        return redirect(reverse("gastos:gestion_catalogos"))


class CentroCostoToggleActivoView(View):
    """Activa o desactiva (baja lógica) un centro de costo existente."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result
        if not _puede_administrar_catalogos(actor):
            raise PermissionDenied("No posee permisos para administrar catálogos.")

        centro = get_object_or_404(CentroCosto, pk=pk)
        centro.activo = not centro.activo
        centro.save(update_fields=["activo"])
        estado_desc = "activado" if centro.activo else "desactivado"
        messages.info(request, f"Centro de costo '{centro.nombre}' {estado_desc}.")
        return redirect(reverse("gastos:gestion_catalogos"))

