# Propuesta de contrato — Adaptador de identidad local permanente

- Estado: PROPUESTA (pendiente de revisión de interfaz y reparto con Matías; no acordado ni validado institucionalmente)
- Contexto: Issue [#109](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/109); complementa [identidad-demo-i1.md](identidad-demo-i1.md); relacionado con [SPEC-016](../specs/016-matias-preparacion-identidad-institucional.md) e Issue [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79).
- Responsables: Matías Alejandro Fernández (componente identidad), Franco Damián Sánchez (propuesta administrativa y consumidor Gastos).

## 1. Propósito y garantías de coexistencia

Define la interfaz pública y garantías del adaptador de identidad local permanente para usuarios sin integración institucional, enlazando con [SPEC-022](../specs/022-franco-acceso-local-administracion.md).

- **Coexistencia de adaptadores**: el modo demo y sus usuarios conservan su contrato vigente (`DEMO_IDENTITY_ENABLED`), sin universalizarles verificación de correo ni aprobación administrativa. El adaptador local requiere habilitación explícita en servidor (`LOCAL_IDENTITY_ENABLED`) y cuenta incorporada expresamente; no autoriza a cualquier usuario de Django ni aplica a otros orígenes.
- **Origen controlado**: ningún consumidor ni cliente selecciona el origen de autenticación mediante parámetros POST, query strings o cabeceras HTTP.
- **Aislamiento institucional**: una integración futura ([SPEC-016](../specs/016-matias-preparacion-identidad-institucional.md)) no otorgará contraseñas locales ni asociará cuentas automáticamente por correo. No se inventan endpoints ni proveedores de Sistemas.

## 2. Firmas públicas e invariantes del Actor

Se preservan estrictamente las firmas vigentes de `identidad/services.py`:

- `Actor(subject_id: int, capabilities: frozenset[str], email_registrado: str | None = None)`: inmutable (`dataclass(frozen=True)`). `subject_id` corresponde al `user.pk` local inmutable, garantizando trazabilidad y titularidad histórica en Gastos y Facturación.
- `resolve_actor(request: HttpRequest) -> Actor | None`: consulta la base en cada petición; la revocación de capacidades o la suspensión de cuentas es inmediata, sin persistir permisos en la sesión ni en cachés.
- `has_capability(actor: Actor | None, code: str) -> bool`: verificación estricta sobre capacidades conocidas. `is_staff` e `is_superuser` no confieren capacidades de negocio implícitas.

## 3. Modelo de estados y resolución

- **Estados del sujeto local**: `REGISTRADO_PENDIENTE_EMAIL`, `EMAIL_VERIFICADO_PENDIENTE_APROBACION`, `ACTIVO`, `RECHAZADO`, `SUSPENDIDO`.
- **Condición local de resolución**: requiere origen local habilitado y cuenta incorporada expresamente. `resolve_actor` genera un `Actor` operativo únicamente si la cuenta local está autenticada, activa (`user.is_active=True`), con correo verificado y estado administrativo `ACTIVO`. En estados previos, en consulta de estado, o ante rechazo/suspensión devuelve `None` frente a trámites. Las condiciones de demo permanecen bajo su contrato propio.
- **Perfil inicial de solicitante**: las capacidades se conceden únicamente DESPUÉS de verificar correo y obtener aprobación administrativa, nunca por el mero registro. El perfil habilitado cubre solicitante de ambos circuitos con capacidades existentes: `gastos.presentar`, `gastos.consultar_propias`, `facturacion.presentar`, `facturacion.consultar_propias`, `facturacion.corregir` y `facturacion.informar_cobro`. Verificar correo y aprobar no inventa facultades documentales ni internas; las capacidades documentales se rigen por el contrato vigente y la composición final del perfil se revisará con Matías antes de implementar, sin adoptar los demo groups como modelo productivo definitivo.

## 4. Seguridad, tokens y aislamiento de correos

- **Tokens temporales**: enlaces de un solo uso con propósito unívoco (`verificacion_email`, `recuperacion_clave`), vinculados a la identidad y al correo. Quedan invalidados tras su uso, cambio de contraseña o cambio de estado.
- **Parámetros técnicos**: duración (TTL) y límites de tasa (rate limiting) para peticiones y reenvíos son parámetros técnicos pendientes del plan, no reglas institucionales.
- **Respuestas neutras y fallos observables**: mensajes públicos homogéneos contra enumeración de usuarios. Los fallos del servicio de correo son observables en backend sin fingir entregas exitosas, admitiendo reintento.
- **Aislamiento de correos y unicidad**: propuesta de correo personal único sólo para nuevas identidades locales, sin imponer unicidad retroactiva a `auth.User.email` ni migrar cuentas existentes; pendiente revisar con Matías convivencia y colisiones antes de implementar. Prohibido reasignar trámites por correo compartido.
