# Contrato — Adaptador de identidad local permanente

- Estado: primer incremento implementado en rama de tarea; revisión compartida y validación institucional pendientes. Ver controles y límites en la [guía de acceso local](../guides/acceso-local.md).
- Contexto: Issue [#109](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/109); complementa [identidad-demo-i1.md](identidad-demo-i1.md); relacionado con [SPEC-016](../specs/016-matias-preparacion-identidad-institucional.md) e Issue [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79).
- Responsables: Matías Alejandro Fernández (componente identidad), Franco Damián Sánchez (propuesta administrativa y consumidor Gastos).

## 1. Propósito y garantías de coexistencia

Define la interfaz pública y garantías del adaptador de identidad local permanente para usuarios sin integración institucional, enlazando con [SPEC-022](../specs/022-franco-acceso-local-administracion.md).

- **Coexistencia e independencia de adaptadores**: el modo demo y sus usuarios conservan su contrato vigente (`DEMO_IDENTITY_ENABLED`). El adaptador local requiere activación explícita en servidor (`LOCAL_IDENTITY_ENABLED`). Si un usuario posee `CuentaLocal`, su resolución se rige exclusivamente por el adaptador local y no existe fallback a demo; una cuenta local pendiente o rechazada no adquiere capacidades de demo. A su vez, usuarios de demo no pueden adquirir capacidades `local_*` ni `identidad.*`.
- **Origen controlado**: ningún consumidor ni cliente selecciona el origen de autenticación mediante parámetros POST, query strings o cabeceras HTTP.
- **Aislamiento institucional**: una integración futura ([SPEC-016](../specs/016-matias-preparacion-identidad-institucional.md)) no otorgará contraseñas locales ni asociará cuentas automáticamente por correo. No se inventan endpoints ni proveedores de Sistemas.

## 2. Firmas públicas e invariantes del Actor

Se preservan estrictamente las firmas vigentes de `identidad/services.py`:

- `Actor(subject_id: int, capabilities: frozenset[str], email_registrado: str | None = None)`: inmutable (`dataclass(frozen=True)`). `subject_id` corresponde al `user.pk` local inmutable, garantizando trazabilidad y titularidad histórica en Gastos y Facturación.
- `resolve_actor(request: HttpRequest) -> Actor | None`: consulta la base en cada petición; la revocación de capacidades o la suspensión de cuentas es inmediata, sin persistir permisos en la sesión ni en cachés.
- `has_capability(actor: Actor | None, code: str) -> bool`: verificación estricta sobre capacidades conocidas. `is_staff` e `is_superuser` no confieren capacidades de negocio implícitas.

## 3. Modelo de estados y resolución

- **Estados del sujeto local**: en `CuentaLocal` rigen `PENDIENTE` (con verificación de buzón separada), `APROBADA` y `RECHAZADA`. La suspensión de cuenta se aplica mediante `user.is_active=False`.
- **Condición local de resolución**: requiere `LOCAL_IDENTITY_ENABLED=True` y cuenta local vinculada. `resolve_actor` genera un `Actor` operativo únicamente si el usuario está autenticado, activo (`user.is_active=True`), con correo verificado (`email_verificado_en is not None`) y estado administrativo `APROBADA`. Las cuentas pendientes o rechazadas tienen sesión limitada a consulta de estado; una cuenta inactiva no puede autenticarse. En todos esos casos no hay `Actor` operativo.
- **Perfil de solicitante local (`local_solicitante`)**: se concede únicamente tras verificación de correo y aprobación administrativa. Agrupa capacidades de presentación y consulta propia en ambos circuitos (`gastos.presentar`, `gastos.consultar_propias`, `facturacion.presentar`, `facturacion.consultar_propias`, `facturacion.corregir`, `facturacion.informar_cobro`) y gestión documental propia (`documentos.incorporar`, `documentos.consultar_metadatos`, `documentos.ver_metadatos`, `documentos.recuperar_contenido`, `documentos.descargar`), manteniendo activos los guards de objeto en cada módulo.
- **Administración local (`local_administracion`)**: concede `identidad.administrar_cuentas` para evaluar altas pendientes en `/cuentas/administracion/altas/`. No confiere facultades de superusuario ni permisos de staff.

## 4. Seguridad, tokens y aislamiento de correos

- **Tokens temporales**: enlaces de verificación firmados con salt específico y expiración (`LOCAL_VERIFICATION_TIMEOUT`). Restablecimiento de contraseña basado en Django estándar con generador extendido `TokenRecuperacionLocal` en `tokens_local.py` (vinculado a hash de contraseña, nonce, estado, correo y actividad).
- **Revocación e invalidación**: la rotación de nonce por cambio de actividad del usuario se ejecuta mediante señal `pre_save` sobre `User.save()`; no garantiza revocación ante escrituras directas por SQL o actualizaciones bulk.
- **Límite de tasa**: control de intentos por IP y por destinatario mediante modelo `LimiteAcceso` sin dependencias externas.
- **Respuestas neutras y fallos observables**: mensajes públicos homogéneos contra enumeración de usuarios. Los fallos del servicio de correo son observables en backend sin fingir entregas exitosas, admitiendo reintento.
- **Aislamiento de correos y unicidad**: unicidad case-insensitive obligatoria solo en `CuentaLocal` (`UniqueConstraint(Lower("email"))`), sin modificar la unicidad ni estructura de `auth.User.email` legado. Se previenen colisiones al registrar. Prohibido reasignar trámites por correo compartido.
