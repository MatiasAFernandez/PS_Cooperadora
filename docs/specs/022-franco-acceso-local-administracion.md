# SPEC-022 — Acceso local permanente y gestión administrativa

- Estado: primer incremento implementado en rama de tarea; revisión compartida y validación institucional pendientes. Ver controles y límites en la [guía de acceso local](../guides/acceso-local.md).
- Issue: [#109](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/109) (relacionadas: [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79), [#77](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/77), [#78](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/78))
- Responsable principal: Franco Damián Sánchez (alcance administrativo y revisión del consumidor Gastos)
- Rol del compañero: Matías Alejandro Fernández (conserva componente identidad)
- Validador: Cooperadora (operación) / Equipo (interfaces)

## Problema y valor

Brindar acceso local permanente y autónomo para usuarios sin integración institucional (ej. personal no docente o colaboradores). Resuelve alta, validación de buzón, control administrativo, autenticación y autogestión de credenciales sin depender de cuentas demo ni anticipar APIs externas.

## Alcance

### Incluye
- Registro público: nombre completo, correo y contraseña obligatorios; área habitual, CUIT/CUIL y legajo opcionales.
- Verificación de buzón por enlace temporal firmado de un solo uso con reenvío limitado (`LimiteAcceso`).
- Aprobación y rechazo administrativo de cuentas pendientes con motivo obligatorio en caso de rechazo (`identidad.administrar_cuentas`).
- Autenticación estándar (login/salida) por correo local sobre Django y consulta de estado propia (`/cuentas/estado/`).
- Recuperación de contraseña por enlace de un solo uso (`TokenRecuperacionLocal`) y cambio voluntario exigiendo contraseña actual.
- Perfil `local_solicitante` con capacidades operativas propias en Gastos y Facturación y gestión documental propia (`documentos.incorporar`, `documentos.consultar_metadatos`, `documentos.ver_metadatos`, `documentos.recuperar_contenido`, `documentos.descargar`), con guards de objeto vigentes.
- Revocación de sesión e invalidación de enlaces ante cambio de actividad (`is_active`) mediante señal `pre_save` sobre `User.save()`.
- Correo personal único para nuevas identidades locales (`CuentaLocal` con `UniqueConstraint(Lower("email"))`).

### No incluye
- Suspensión interactiva por interfaz web (se gestiona mediante `user.is_active=False`; la bandeja actual evalúa únicamente solicitudes pendientes).
- ABM general de usuarios ni editor de cambio de correo.
- Proveedor o endpoint institucional de Sistemas ni SSO (mantenido bajo [SPEC-016](016-matias-preparacion-identidad-institucional.md) e Issue [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79)).
- Unicidad retroactiva sobre `auth.User.email` ni migración obligatoria de cuentas legadas (la unicidad rige sobre `CuentaLocal`, previniendo colisiones).
- No garantiza invalidación de enlaces ante escrituras directas por SQL o actualizaciones bulk sin ejecución de `User.save()`.
- Prohíbe autoasignación de facultades internas y concesión operativa previa a la habilitación formal.
- Avisos generales de trámites ni dispensas ([#78](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/78)).
- Configuración SMTP de producción ni proveedor definitivo; URL base canónica vía `LOCAL_PUBLIC_BASE_URL`.

## Recorrido y reglas de negocio

1. **Flujo de estados**: en `CuentaLocal` rigen `PENDIENTE`, `APROBADA` y `RECHAZADA`. La suspensión operativa se rige mediante `user.is_active=False`.
2. **Verificación y acceso**: verificar el buzón acredita control de la casilla, no pertenencia institucional ni acceso operativo. Cuentas no aprobadas o sin verificar acceden únicamente a consulta de estado (`/cuentas/estado/`) sin entrega de `Actor` operativo ni fallback a demo.
3. **Acceso efectivo**: tras verificación de correo y aprobación administrativa formal, la cuenta activa resuelve el perfil `local_solicitante` para ambos circuitos según [identidad-local.md](../contracts/identidad-local.md), sin otorgar facultades internas ni alterar las condiciones de cuentas demo.
4. **Administración**: la bandeja administrativa (`/cuentas/administracion/altas/`) exige la capacidad `identidad.administrar_cuentas` (sin facultades implícitas por staff o superusuario), requiere motivo obligatorio en rechazos y prohíbe autodecisión.
5. **Credenciales**: recuperar o cambiar contraseña no aprueba cuentas, no verifica correo ni levanta suspensiones.
6. **Diferenciación de correos**: el correo personal de acceso/recuperación es independiente del correo de área (agrupación de contacto) y del destinatario de comprobantes. La titularidad histórica (`user.pk`) se preserva sin mezclar personas por correo.

## Criterios de aceptación

1. **Acceso y habilitación**: sin verificación de correo o aprobación administrativa, no hay acceso a trámites por interfaz ni por URL directa. Tras la habilitación formal, el solicitante puede presentar y consultar sus trámites propios en Gastos y Facturación (`gastos.presentar`, `gastos.consultar_propias`, `facturacion.presentar`, `facturacion.consultar_propias`, `facturacion.corregir`, `facturacion.informar_cobro`), denegándosele trámites ajenos y acciones internas u operativas de decisión o pago.
2. **Ciclo de enlaces**: tokens de verificación y recuperación son de un solo uso, caducan por tiempo y se invalidan tras uso o cambio de clave/estado.
3. **Reenvío y fallos**: reenvío con tasa límite; caídas del email son observables en backend sin simular entrega, permitiendo reintentar.
4. **Concurrencia**: registros simultáneos con el mismo correo propuesto o decisiones administrativas concurrentes no generan duplicados ni estados corruptos.
5. **Suspensión inmediata**: cuenta suspendida pierde resolución de `Actor` en la siguiente petición, incluso con sesión previa.
6. **No invasión histórica**: correo compartido existente en trámites previos no altera solicitantes históricos ni fusiona registros.
7. **Anti-enumeración**: formularios públicos emiten respuestas neutras que impiden deducir existencia de cuentas.
8. **Pruebas sintéticas**: cambio y reseteo probados con sesiones sintéticas y backend de email simulado; proveedor, remitente y URL base reales quedan por configurar.

## Experiencia de usuario (UX/UI)

Sigue la [Guía visual](../visual-guide/README.md) y formularios operativos actuales. Diseño accesible y adaptable a escritorio y móvil (390px, sin desbordes). Conservación de datos ingresados no sensibles ante error, scroll y foco en el primer control inválido, y mensajes de estado explícitos sin textos defensivos.

## Plan de incrementos y dependencias

- **Núcleo de persistencia y verificación**: publicado en la rama de tarea en `b42cd8a` (modelo `CuentaLocal`, migración `0001_initial`, lógica en `identidad.cuentas` y limitación de tasa).
- **Capa HTTP y UI local**: implementada en rama `feat/109-acceso-local` (`urls_local`, `views_local`, `forms_local`, `tokens_local` y plantillas de `/cuentas/`), pendiente de revisión compartida. Procedimiento y alcance de las comprobaciones en la [guía de acceso local](../guides/acceso-local.md).
- **Límites pendientes**: configuración SMTP de producción, suspensión interactiva en interfaz web y ABM general de usuarios.
