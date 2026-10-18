"""Vistas para el circuito de gastos."""

from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from gastos.auth import has_capability, resolve_actor
from gastos.contracts import (
    TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    DocumentVerificationError,
    OpcionDocumental,
)
from gastos.document_provider import cargar_proveedor_documental
from gastos.forms import (
    DecisionGastoForm,
    FiltroEstadoGastoForm,
    PagoExternoForm,
    SolicitudGastoForm,
)
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from gastos.payments import (
    PaymentConflictError,
    PaymentExpenseNotFoundError,
    PaymentInvalidExpenseStateError,
    PaymentInvalidInputError,
    PaymentPermissionDeniedError,
    consultar_pago_externo,
    derivar_categoria_respaldo,
    registrar_pago_externo,
)
from gastos.queries import visible_expenses
from gastos.services import (
    ConcurrencyConflictError,
    ExpenseNotFoundError,
    ExpensePermissionDeniedError,
    InvalidDecisionInputError,
    InvalidTransitionError,
    can_decide_expense,
    crear_solicitud_gasto,
    decide_expense,
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
    try:
        opciones = list(
            proveedor.listar_opciones_para_pago(
                actor=actor,
                gasto=solicitud,
                tipos_admitidos=TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
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
        if tipo not in TIPOS_DOCUMENTO_ADMITIDOS_PAGO:
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



class SolicitudGastoCreateView(View):
    """Presentación de una nueva solicitud de gasto."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.presentar"):
            raise PermissionDenied("No posee capacidad para presentar gastos.")

        form = SolicitudGastoForm()
        return render(
            request,
            "gastos/solicitud_form.html",
            {"form": form, "actor": actor},
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.presentar"):
            raise PermissionDenied("No posee capacidad para presentar gastos.")

        form = SolicitudGastoForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "gastos/solicitud_form.html",
                {"form": form, "actor": actor},
                status=200,
            )

        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto=form.cleaned_data["concepto"],
            monto_estimado=form.cleaned_data["monto_estimado"],
            unidad_requirente=form.cleaned_data["unidad_requirente"],
        )

        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))


class SolicitudGastoListView(View):
    """Listado de solicitudes de gasto visibles para el actor."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        solicitudes = visible_expenses(actor)
        filtro_form = FiltroEstadoGastoForm(request.GET)
        if filtro_form.is_valid():
            estado = filtro_form.cleaned_data["estado"]
            if estado:
                solicitudes = solicitudes.filter(estado=estado)
            concepto = filtro_form.cleaned_data["q"]
            if concepto:
                solicitudes = solicitudes.filter(concepto__icontains=concepto)
        else:
            solicitudes = solicitudes.none()
        return render(
            request,
            "gastos/solicitud_list.html",
            {"solicitudes": solicitudes, "actor": actor, "filtro_form": filtro_form},
        )


def _solicitud_detail_context(actor: Any, solicitud: Any) -> dict[str, Any]:
    """Construye el contexto compartido por el detalle y sus errores de decisión."""
    decisiones = solicitud.decisiones.all()
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
    cronologia.sort(
        key=lambda evento: (
            evento.fecha_hora is None,
            evento.fecha_hora,
            evento.evento_id,
        )
    )

    can_decide = any(
        can_decide_expense(actor, solicitud, act)
        for act in ("aceptar", "postergar", "rechazar")
    )
    decision_form = (
        DecisionGastoForm(initial={"version": solicitud.version}) if can_decide else None
    )
    # Acción de pago: requiere ambos permisos, estado aceptado y ausencia de pago.
    # La mera presencia de configuración no invoca al proveedor ni lista opciones.
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
    puede_registrar_pago = (
        mostrar_estado_registro_pago
        and pago_permiso_registrar
        and pago_permiso_metadatos
    )
    pago_provider_configurado = (
        cargar_proveedor_documental() is not None if puede_registrar_pago else False
    )

    respaldo_categoria = None
    if pago_consulta is not None and has_capability(actor, "documentos.ver_metadatos"):
        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is not None:
            _, opciones = carga
            referencia_doc = (
                PagoExterno.objects.filter(solicitud=solicitud)
                .values_list("referencia_documental", flat=True)
                .first()
            )
            respaldo_categoria = derivar_categoria_respaldo(referencia_doc, opciones)

    return {
        "solicitud": solicitud,
        "actor": actor,
        "tramite_id": f"gastos:{solicitud.pk}",
        "decisiones": decisiones,
        "pago_consulta": pago_consulta,
        "cronologia": cronologia,
        "can_decide": can_decide,
        "decision_form": decision_form,
        "mostrar_estado_registro_pago": mostrar_estado_registro_pago,
        "puede_registrar_pago": puede_registrar_pago,
        "pago_permiso_registrar": pago_permiso_registrar,
        "pago_permiso_metadatos": pago_permiso_metadatos,
        "pago_provider_configurado": pago_provider_configurado,
        "mensaje_respaldo": solicitud.mensaje_respaldo,
        "respaldo_categoria": respaldo_categoria,
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
        return render(
            request,
            "gastos/solicitud_detail.html",
            _solicitud_detail_context(actor, solicitud),
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
                form = DecisionGastoForm(data=request.POST)
                form.is_valid()
                form.add_error("motivo" if "motivo" in str(exc).lower() else None, str(exc))
                context = _solicitud_detail_context(actor, solicitud)
                context.update(
                    {
                        "decision_form": form,
                        "error_decision": str(exc),
                    }
                )
                return render(
                    request,
                    "gastos/solicitud_detail.html",
                    context,
                    status=400,
                )
            return HttpResponse(str(exc), status=400)
        except (ConcurrencyConflictError, InvalidTransitionError) as exc:
            return HttpResponse(str(exc), status=409)

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return HttpResponseNotAllowed(["POST"])


class SolicitudGastoPagoView(View):
    """Formulario y registro del pago externo de una solicitud aceptada.

    Orden de comprobaciones (idéntico en GET y POST):
    1. `_enforce_actor` (identidad de sesión).
    2. 404 sobre `visible_expenses(actor)` antes de cualquier permiso.
    3. Capacidad explícita `gastos.registrar_pago` (403).
    4. Si ya existe pago: bypass idempotente C03 con `document_provider=None`,
       sin listar ni leer metadatos y sin exigir proveedor disponible.
    5. Para alta nueva: capacidad `documentos.ver_metadatos` (403) antes de
       invocar al proveedor o a su listado.
    6. Proveedor o listado ausente/con error, o selector sin la versión enviada:
       antes de cerrar con 503/400 se reconsulta el pago. Si en la ventana otra
       petición ya confirmó el pago, el reenvío se resuelve con C03 sin proveedor
       (idéntico 302, distinto 409). Sin pago confirmado se conserva el cierre
       fail-closed (503/400).
    7. Entrada inválida sin pago confirmado: 400 con formulario y contexto.
    8. Estado o contenido conflictivo: 409. Fallo documental: 409 genérico.
    9. Éxito: redirección al detalle.

    La vista nunca acepta una referencia documental fuera del listado vigente ni
    deriva el proveedor de datos enviados por el cliente.
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

        # Sólo un gasto aceptado y sin pago muestra el formulario. La ruta directa
        # en cualquier otro caso redirige al detalle sin exponer el formulario.
        if _pago_externo_registrado(solicitud) or solicitud.estado != EstadoSolicitud.ACEPTADA:
            return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

        if not has_capability(actor, "documentos.ver_metadatos"):
            raise PermissionDenied("No posee capacidad para consultar metadatos documentales.")

        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is None:
            return _servicio_pago_no_disponible()
        _, opciones = carga

        form = PagoExternoForm(opciones_documentales=opciones)
        return render(
            request,
            self.template_name,
            self._contexto_pago(actor, solicitud, form, opciones),
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)

        if not has_capability(actor, "gastos.registrar_pago"):
            raise PermissionDenied("No posee capacidad para registrar pagos.")

        # Reenvío sobre un pago ya persistido: idempotencia sin proveedor ni listado.
        if _pago_externo_registrado(solicitud):
            return self._reenviar_pago_existente(request, actor, solicitud)

        if solicitud.estado != EstadoSolicitud.ACEPTADA:
            form = PagoExternoForm(request.POST, opciones_documentales=[])
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

        if not has_capability(actor, "documentos.ver_metadatos"):
            raise PermissionDenied("No posee capacidad para consultar metadatos documentales.")

        carga = _cargar_opciones_documentales(actor, solicitud)
        if carga is None:
            reenvio = self._reenviar_si_aparecio_pago(request, actor, solicitud)
            if reenvio is not None:
                return reenvio
            return _servicio_pago_no_disponible()
        proveedor, opciones = carga

        form = PagoExternoForm(request.POST, opciones_documentales=opciones)
        if not form.is_valid():
            # La opción puede haber desaparecido del catálogo vigente. Antes de
            # cerrar con 400 se reconsulta el pago: una confirmación concurrente
            # se resuelve por C03 y nunca convierte la sola existencia en éxito.
            reenvio = self._reenviar_si_aparecio_pago(request, actor, solicitud)
            if reenvio is not None:
                return reenvio
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=400,
            )

        try:
            registrar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                importe=form.cleaned_data["importe"],
                fecha_pago=form.cleaned_data["fecha_pago"],
                referencia_externa=form.cleaned_data["referencia_externa"],
                referencia_documental=form.cleaned_data["referencia_documental"],
                document_provider=proveedor,
            )
        except PaymentExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except PaymentPermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except PaymentInvalidInputError as exc:
            form.add_error(None, str(exc))
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
        except PaymentConflictError:
            return HttpResponse(
                "Ya existe un pago registrado con datos diferentes.", status=409
            )
        except DocumentVerificationError:
            # Respuesta deliberadamente genérica: sin texto del proveedor ni
            # detalle documental (referencia, versión o tipo). Se conservan los
            # campos ingresados y se refresca el selector cuando el proveedor
            # puede entregar las versiones vigentes.
            opciones_actualizadas = _listar_opciones_documentales(
                proveedor, actor, solicitud
            )
            if opciones_actualizadas is not None:
                opciones = opciones_actualizadas
                form = PagoExternoForm(
                    request.POST, opciones_documentales=opciones_actualizadas
                )
            form.add_error(None, "No se pudo verificar el respaldo documental del pago.")
            return render(
                request,
                self.template_name,
                self._contexto_pago(actor, solicitud, form, opciones),
                status=409,
            )

        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))

    def _reenviar_pago_existente(
        self, request: HttpRequest, actor: Any, solicitud: Any
    ) -> HttpResponse:
        """Reenvía un alta ya persistida sin proveedor ni listado documental para C03.

        La llamada al servicio C03 recibe document_provider=None y no lista ni
        verifica documentos para la resolución del reenvío: compara la huella y
        todos los campos normalizados; un reenvío idéntico redirige al detalle
        sin nuevo evento ni proveedor, y un contenido distinto responde 409.
        Ante un error por entrada malformada (PaymentInvalidInputError) se
        renderiza el detalle del gasto pagado, donde C04 puede realizar una
        consulta separada al listado vigente ante el proveedor si el actor posee
        la capacidad documentos.ver_metadatos; esta consulta deriva una
        categoría factual de visualización, nunca expone la referencia documental
        almacenada y no autoriza ni muta el pago.
        """
        try:
            registrar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                importe=request.POST.get("importe"),
                fecha_pago=request.POST.get("fecha_pago"),
                referencia_externa=request.POST.get("referencia_externa"),
                referencia_documental=request.POST.get("referencia_documental"),
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
        """Reconoce un pago confirmado durante la ventana de una salida preliminar.

        La vista decide una sola vez al inicio; otra petición puede confirmar el
        pago mientras se carga el listado documental o el selector. Antes de
        cerrar por proveedor/selector se reconsulta la persistencia: la sola
        existencia habilita *intentar* C03, que conserva la normalización, la
        comparación autoritativa de campos y huella, la reautorización y la
        ausencia de escrituras duplicadas. Sin pago confirmado devuelve `None`
        para conservar el cierre fail-closed de un alta nueva.
        """
        if not _pago_externo_registrado(solicitud):
            return None
        return self._reenviar_pago_existente(request, actor, solicitud)

    @staticmethod
    def _contexto_pago(
        actor: Any,
        solicitud: Any,
        form: PagoExternoForm,
        opciones: list[OpcionDocumental],
        *,
        formulario_habilitado: bool = True,
    ) -> dict[str, Any]:
        return {
            "solicitud": solicitud,
            "actor": actor,
            "form": form,
            "opciones_documentales": opciones,
            "formulario_habilitado": formulario_habilitado,
            "tramite_id": f"gastos:{solicitud.pk}",
        }
