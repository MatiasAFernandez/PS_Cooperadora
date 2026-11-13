# SPEC-026 — Asignación administrativa de perfiles locales

- Estado: alcance autorizado; implementación y verificaciones pendientes.
- Issue: [#121](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/121).
- Franco Damián Sánchez define alcance administrativo; Matías Alejandro Fernández conserva identidad. Su revisión no se presume.
- Extiende SPEC-023/024/025. No cambia las capacidades ni la firma de Actor.

## Catálogo fijo

Los perfiles exponen grupos ya reconocidos por identidad, sin crear nuevas facultades ni atribuir cargos institucionales. Las combinaciones son explícitas; administrar cuentas no concede pagos, decisiones o configuración automáticamente.

| Perfil visible | Grupo existente gestionado | Alcance actual |
|---|---|---|
| Solicitante | local_solicitante | Presentación y consulta propia de ambos circuitos y documentación propia según permisos actuales. |
| Administración de cuentas | local_administracion | Gestión de cuentas locales. |
| Configuración de formularios | demo_administracion | Configuración mediante gestion.configurar. |
| Operación de gastos | demo_operadora | Consulta global y decisión de gastos. |
| Registro de pagos | demo_gastos_pago | Registro de pagos externos. |
| Lectura global de gastos | demo_lectura | Consulta global de gastos. |
| Operación de facturación | demo_facturacion_operadora | Consulta global, observación y registro externo de facturas/cobros. |
| Lectura global de facturación | demo_facturacion_lectura | Consulta global de facturación. |
| Aporte documental | demo_documentos_aporte | Incorporación según las autorizaciones por objeto vigentes. |
| Revisión documental | demo_documentos_revision | Revisión documental. |
| Consulta documental | demo_documentos_metadatos | Consulta de metadatos. |
| Descarga documental | demo_documentos_descarga | Recuperación/descarga autorizada. |
| Verificación de cobros | demo_verificacion_cobros | Verificación de cobros. |
| Cierre y regularización de facturación | demo_resolucion_facturacion | Cierre, anulación y actualización de respaldo. |

Los nombres internos históricos no se presentan como etiquetas de producto. No se gestionan aquí demo_solicitante ni demo_facturacion_solicitante: sus pertenencias y cualquier otro grupo fuera del catálogo se conservan. No se convierten ni migran usuarios legados por correo. La interfaz advierte cuando se conservan grupos ajenos al catálogo, sin ofrecer su eliminación.

## Recorrido y reglas

Desde la ficha, «Gestionar perfiles» muestra la persona, su estado y selecciones actuales con descripciones. Guardar requiere motivo obligatorio de hasta 2000 caracteres y POST con CSRF; cancelar vuelve a la ficha con los filtros. Sólo administra un actor con identidad.administrar_cuentas actualmente habilitado. Staff/superusuario no conceden facultades implícitas. No se permite cambiar los perfiles propios.

Asignar perfiles no verifica, aprueba o activa cuentas ni cambia correo o contraseña. Cuenta pendiente, rechazada, sin verificar o inactiva sigue sin operación. Los permisos efectivos se resuelven de nuevo en cada petición con las reglas actuales; no se mantienen permisos en sesión.

La selección acepta sólo claves del catálogo. Modifica únicamente esos grupos y conserva los demás. Selección vacía retira sólo los gestionados. Una referencia firmada de la selección inicial rechaza confirmaciones obsoletas sin sobrescribir cambios posteriores. Envío idéntico no genera evento; reenvío del cambio ya aplicado no duplica el hecho.

## Atomicidad y administración disponible

Revalidar al actor y proteger el último administrador habilitado con el mismo orden de bloqueo de User/CuentaLocal del servicio de actividad. Extraer y compartir sólo ese protocolo concreto evita divergencias entre dos flujos que modifican la disponibilidad administrativa. No se crea un motor genérico de permisos/bloqueos.

Un administrador cuenta sólo si está activo, aprobado, verificado y conserva capacidad efectiva según GROUP_CAPABILITIES, incluyendo grupos conservados. Carrera de retirada de perfiles entre administradores y carrera mixta con desactivación no pueden dejar cero administradores. Cambios M2M e historial se confirman juntos; error revierte ambos.

Historial específico con autor, fecha, motivo y perfiles gestionados anteriores/nuevos, sin sesiones, tokens ni POST completos. Ficha con perfiles seleccionados y sección paginada a diez eventos, separada de los historiales existentes. El flujo sólo agrega historia; no garantiza inmutabilidad frente a SQL directo.

## Diseño y aceptación

Reutilizar shell, ficha, formularios y guía visual. Opciones con nombres/descripciones comprensibles, agrupadas por circuito/función; Guardar perfiles y Cancelar juntos, errores y recarga visibles. Sin editor de códigos, permisos arbitrarios o botones de funciones futuras. Revisar escritorio y móvil de 390 px.

Pruebas: GET/POST autorizados, CSRF, claves inválidas, grupos conservados, no-op, referencia obsoleta, prohibición de cambios propios, actividad/aprobación/verificación y credenciales intactas, efecto en la siguiente petición, rollback, carrera cruzada y mixta en PostgreSQL. Regresión focal de actividad y de la ficha anterior. QA de navegador se registra por separado.

Alta administrativa, SSO y notificaciones siguen como hitos separados. Esta matriz es técnica; la asignación de responsables institucionales sigue requiriendo validación.
