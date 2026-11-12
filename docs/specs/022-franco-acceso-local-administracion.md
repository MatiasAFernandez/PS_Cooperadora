# SPEC-022 — Acceso local permanente y gestión administrativa

- Estado: PROPUESTA (pendiente de revisión de interfaz y reparto con Matías; no acordado ni validado institucionalmente)
- Issue: [#109](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/109) (relacionadas: [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79), [#77](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/77), [#78](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/78))
- Responsable principal: Franco Damián Sánchez (alcance administrativo y revisión del consumidor Gastos)
- Rol del compañero: Matías Alejandro Fernández (conserva componente identidad)
- Validador: Cooperadora (operación) / Equipo (interfaces)

## Problema y valor

Brindar acceso local permanente y autónomo para usuarios sin integración institucional (ej. personal no docente o colaboradores). Resuelve alta, validación de buzón, control administrativo, autenticación y autogestión de credenciales sin depender de cuentas demo ni anticipar APIs externas.

## Alcance

### Incluye
- Registro público: nombre, correo y contraseña obligatorios; área habitual, CUIT/CUIL y legajo opcionales.
- Verificación de buzón por enlace temporal de un solo uso con reenvío limitado.
- Aprobación, rechazo y suspensión de cuentas exclusivamente por administración.
- Autenticación estándar (login/salida) sobre Django 5.2.
- Recuperación de contraseña por enlace de un solo uso y cambio voluntario exigiendo contraseña actual.
- Propuesta de correo personal único sólo para NUEVAS identidades locales.

### No incluye
- Proveedor o endpoint institucional de Sistemas (mantenido bajo [SPEC-016](016-matias-preparacion-identidad-institucional.md) e Issue [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79)).
- No decide como hecho email-as-login, plazos institucionales ni proveedor SMTP.
- Unicidad retroactiva sobre `auth.User.email` ni migración obligatoria de cuentas existentes.
- Prohíbe autoasignación de facultades internas (revisión, decisión, pago, administración) y cualquier concesión operativa previa a la habilitación formal, sin restringir las acciones del solicitante una vez habilitado.
- Avisos generales de trámites ni dispensas ([#78](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/78)).
- Editor de cambio de correo (requerirá verificar nuevo destino antes de recuperaciones).
- Criptografía propietaria ni colas genéricas; reutiliza utilidades estándar de Django 5.2.

## Recorrido y reglas de negocio

1. **Flujo de estados**: `registro` -> `verificar buzón` -> `pendiente de aprobación` -> `activo` (o `rechazado` / `suspendido`).
2. **Verificación y acceso**: verificar el buzón acredita control de la casilla, no pertenencia institucional ni acceso operativo. Una sesión para consultar el estado no entrega `Actor` operativo.
3. **Acceso efectivo**: tras verificación de correo y aprobación administrativa formal, la cuenta activa resuelve el perfil solicitante para ambos circuitos según [identidad-local.md](../contracts/identidad-local.md), sin otorgar facultades internas ni alterar las condiciones de cuentas demo.
4. **Credenciales**: recuperar o cambiar contraseña no aprueba cuentas, no verifica correo ni levanta suspensiones.
5. **Diferenciación de correos**: el correo personal de acceso/recuperación es independiente del correo de área (agrupación de contacto) y del destinatario de comprobantes. La titularidad histórica (`user.pk`) se preserva sin mezclar personas por correo.

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

- **Inc. 1**: Formalización de interfaz y revisión de convivencia con Matías ([identidad-local.md](../contracts/identidad-local.md)).
- **Inc. 2**: Persistencia de estados locales y flujo de verificación de correo (backend simulado en desarrollo/test).
- **Inc. 3**: Vistas de login, salida, recuperación y cambio de clave.
- **Inc. 4**: Bandeja administrativa de aprobación/rechazo/suspensión ([#77](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/77)).
- **Límites**: Parámetros de TTL, límites de tasa y configuración SMTP final quedan sujetos al plan de despliegue.
