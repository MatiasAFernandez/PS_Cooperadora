# SPEC-027 — Alta administrativa mediante invitación

- Estado: núcleo y recorrido HTTP implementados en rama de tarea; revisión y prueba visual pendientes.
- Issue: [#123](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/123).
- Franco Damián Sánchez define alcance administrativo; Matías Alejandro Fernández conserva identidad. Su revisión no se presume.
- Complementa SPEC-022 y la gestión local de SPEC-023 a SPEC-026.

## Recorrido y permisos

«Nueva cuenta» desde Usuarios abre un formulario administrativo de nombre completo, correo, área habitual, CUIT / CUIL y legajo, con las reglas de datos del alta actual. No incluye contraseña, aprobación, actividad ni perfiles. Crear y reenviar exigen identidad.administrar_cuentas vigente, comprobada en servidor y al guardar; staff/superusuario no conceden permisos implícitos.

Crear genera User activo con contraseña no utilizable y CuentaLocal PENDIENTE sin correo verificado ni facultades operativas. La invitación identifica origen, autor y fecha. Un correo duplicado en CuentaLocal o User legado se informa a administración sin reasignar identidades, convertir una cuenta existente ni cambiar sus credenciales. Conflictos no dejan User huérfano.

El titular abre el correo y, mediante POST con CSRF, confirma su contraseña nueva. Se aplican validadores de Django y coincidencia de claves. Aceptar prueba control del buzón y establece la contraseña de ese titular: no aprueba la cuenta ni cambia actividad o perfiles. Después puede iniciar sesión para consultar su estado, y administración continúa con la bandeja de aprobación existente.

## Enlaces y datos

Una invitación explícita relacionada uno a uno con CuentaLocal distingue este origen sin alterar identidades previas. Registra creador, fecha, aceptación y estado/fecha del último intento de envío, sin conservar token, contraseña ni errores SMTP con datos sensibles.

El enlace usa firma de Django con propósito distinto de verificación/recuperación, vinculado a cuenta, correo, nonce y estado actual de credenciales. Caduca con LOCAL_VERIFICATION_TIMEOUT. GET sólo presenta el formulario. POST acepta una vez y guarda contraseña, verificación, invalidación y aceptación atómicamente. Un enlace consumido, corrupto, vencido, reenviado o de cuenta inactiva/rechazada se rechaza sin modificar datos. Nunca sustituye una contraseña ya establecida.

Se conserva la rotación por cambio de actividad. Reenviar invalida el enlace anterior y limita frecuencia con los mecanismos existentes. La ruta pública de reenvío mantiene mensaje neutro y selecciona invitación o verificación normal según origen y estado; no deja una cuenta invitada con un enlace que no permite completar su acceso. Registro público y recuperación ordinaria conservan sus garantías, incluida la exclusión de contraseñas no utilizables en recuperación.

## Envío y fallos

La cuenta persiste antes de intentar SMTP. Fallo de envío deja un estado visible y permite reintento limitado, sin duplicar la cuenta ni fingir envío correcto. Éxito SMTP acredita aceptación por el backend, no entrega en un buzón externo. Usar URL canónica de configuración, nunca Host o URL aportados por el cliente. En desarrollo se prueba con Mailpit; proveedor/dominio productivos siguen separados.

## Interfaz y aceptación

Reutilizar shell, formulario y ficha de cuentas. Crear/Cancelar juntos, campos y errores claros, conservación de datos no sensibles. Ficha muestra origen, estado de invitación y reenvío cuando corresponde. No mostrar claves ni enlaces firmados a administración. Confirmación pública explica el paso de aprobación pendiente; errores de contraseña no repueblan contraseñas. Formularios con no-store y política same-origin compatible con CSRF, preservando el cierre de B1.

Pruebas: autorización y actor revocado, datos/duplicados y conflicto sin huérfanos, GET sin consumo, validez temporal y replay, reenvío y límites, SMTP fallido con cuenta preservada, aceptación atómica, contraseña válida y aprobación pendiente, bloqueo de cuenta inactiva/rechazada y conservación de credenciales establecidas, ruta pública neutra y regresión del registro/recuperación. Verificar escritorio y móvil de 390 px. No se atribuye prueba de navegador a Django Client.

Fuera de este hito: cambio de correo, SSO, SMTP productivo, asignación de cargos y notificaciones generales de trámites. No hay activación ni aprobación automática por invitación.
