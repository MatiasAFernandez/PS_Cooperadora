# SPEC-025 — Desactivación y reactivación de cuentas locales

- Estado: núcleo y recorrido HTTP implementados en rama de tarea; revisión y prueba visual pendientes.
- Issue: [#119](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/119).
- Franco Damián Sánchez define el alcance administrativo; Matías Alejandro Fernández conserva identidad. No se presume revisión compartida.
- Extiende la ficha de SPEC-023/024 y las garantías de revocación de SPEC-022.

## Recorrido

Desde la ficha, «Desactivar cuenta» o «Reactivar cuenta» abre una confirmación que identifica a la persona, su actividad actual y el efecto de la acción. Motivo obligatorio, con máximo de 2000 caracteres. Confirmar requiere POST con CSRF; cancelar no cambia nada y vuelve a la ficha conservando filtros. No se ejecutan acciones por GET.

La reactivación sólo modifica `User.is_active`: no verifica correo, no aprueba una cuenta pendiente o rechazada, ni cambia contraseña, perfiles o titularidad. La confirmación lo explica brevemente. La actividad continúa mostrándose separada de verificación y aprobación. No se borra la cuenta ni su historia.

## Permisos y protección administrativa

GET y POST requieren `identidad.administrar_cuentas` y bandera local activa; no hay facultades implícitas por staff/superusuario. El servicio vuelve a comprobar que el actor es un administrador local actualmente activo, aprobado, verificado y con la capacidad efectiva. No se permite autodesactivación.

No puede quedar el sistema sin un administrador local habilitado. Sólo cuentan personas que podrían resolver esa capacidad con las reglas actuales de identidad: no basta un grupo de una cuenta pendiente, rechazada, sin verificar o inactiva. Cambios de actividad concurrentes entre administradores se serializan mediante bloqueos en orden estable y revalidación posterior; dos solicitudes cruzadas no pueden desactivar a ambos. No se crea un motor genérico de bloqueos.

## Persistencia y revocación

- Transacción única para actividad, evento y revocación. El evento específico conserva cuenta, autor, fecha, motivo y actividad anterior/nueva. Error de persistencia revierte todo.
- Guardar mediante `User.save(update_fields=["is_active"])` conserva la señal existente de rotación de enlaces. No se modifican directamente contraseña, correo, estados administrativos ni grupos.
- Invalidar las sesiones de esa persona en el almacenamiento actual de Django en base de datos, tanto al desactivar como al reactivar; no tocar sesiones de otras personas. Una sesión anterior no vuelve a operar después de reactivar. La cuenta reactivada debe iniciar sesión nuevamente.
- El mecanismo se limita al motor de sesiones actual; un cambio de motor requiere revisar la revocación. Para el volumen de esta aplicación se admite recorrer sesiones vigentes y eliminar únicamente las correspondientes a la persona, sin agregar infraestructura de autenticación.
- Envío repetido con el estado ya aplicado no agrega evento ni reenvía comunicaciones; no-op explícito. Una confirmación obsoleta que aún implicaría cambiar el estado se rechaza sin sobrescribir.
- Historial de actividad separado del historial de datos básicos, paginado a 10 eventos, sólo para administración. No guardar sesiones, tokens ni POST completos como evidencia.

## Límites y aceptación

Protecciones garantizadas mediante este servicio; no frente a SQL directo, bulk updates u otros flujos que lo eludan. Sin cambio de perfiles, cambio de credenciales, SSO, dispensas o envío de correos en este hito. La futura gestión de perfiles debe conservar la protección del último administrador.

Probar permisos GET/POST, motivo, CSRF, autodesactivación, elegibilidad administrativa, carrera cruzada en PostgreSQL, no-op, confirmación obsoleta, rollback, invalidez de sesiones y enlaces tras desactivar/reactivar, conservación de estados/credenciales y acceso sólo mediante nueva sesión habilitada. Verificar confirmación, errores e historia en escritorio y móvil de 390 px, conservando el shell y los componentes de usuarios. Pruebas HTTP no sustituyen QA de navegador.
