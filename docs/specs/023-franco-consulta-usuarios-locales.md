# SPEC-023 — Consulta administrativa de usuarios locales

- Estado: primer hito integrado mediante PR #116 y verificado en navegador; revisión compartida y validación institucional separadas.
- Issue: [#115](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/115).
- Responsable del alcance administrativo: Franco Damián Sánchez. Matías Alejandro Fernández conserva responsabilidad sobre identidad; este documento no atribuye su conformidad.
- Complementa [SPEC-022](022-franco-acceso-local-administracion.md) y el [contrato de identidad local](../contracts/identidad-local.md).

## Resultado y límites

Administración consulta cuentas locales desde un listado y una ficha. Este hito no modifica usuarios, aprobaciones, perfiles ni sesiones. Alta administrativa, edición y suspensión/reactivación siguen como incrementos posteriores; los usuarios legados sin `CuentaLocal` no se incorporan automáticamente.

## Permisos

Ambas rutas requieren identidad local habilitada y un actor con `identidad.administrar_cuentas`, igual que la bandeja de altas. Staff, superusuario, operación de Gastos o configuración de formularios no conceden acceso implícito. La autorización se comprueba en servidor antes de consultar una ficha. Sin bandera local, las rutas responden 404; sin capacidad, 403. Un identificador inexistente devuelve 404 sólo después de autorizar.

## Composición y comportamiento

- Entrada «Usuarios» en Gestión para el administrador autorizado; título «Usuarios locales» y acceso a «Solicitudes de cuenta» existente.
- Listado paginado de 25 cuentas, orden estable por nombre e identificador, con nombre, correo, área y estados independientes de aprobación, verificación del buzón y actividad.
- Búsqueda por nombre, correo o área. Filtros independientes de aprobación, correo verificado y actividad. Valores inválidos muestran errores; no amplían silenciosamente los resultados.
- Filtros conservados al paginar y volver desde una ficha, sin redirecciones arbitrarias.
- Ficha de consulta: nombre, correo, área habitual, CUIT / CUIL, legajo, estados, fecha de alta y decisión administrativa existente (autor, fecha y motivo cuando corresponda). Datos opcionales vacíos se presentan como «Sin informar».
- No mostrar contraseña, token, nonce, huellas de credenciales, datos bancarios ni trámites. No crear botones que prometan edición aún inexistente.
- GET no escribe y POST no está admitido. Respuestas con datos personales no se almacenan en caché.

## Diseño

Aplicar la [guía visual](../visual-guide/README.md). Conservar shell, navegación, tipografía y componentes de cuentas. Adaptar la composición de padrón y ficha del mockup de usuarios de administración, sin copiar sus cifras, cargos ni funciones propuestas como reglas vigentes. Búsqueda y filtros primero; resultados con enlace «Ver ficha»; ficha con «Volver al listado» y enlace a la bandeja existente. Comprobar escritorio y móvil de 390 px, etiquetas y estados vacíos.

## Aceptación

1. Administrador con capacidad accede; anónimo, solicitante y staff/superusuario sin ella no obtienen datos por URL directa.
2. Búsqueda, filtros combinados, orden y paginación funcionan sobre datos sintéticos sin consultas por cada fila.
3. Ficha autorizada e inexistente distinguidas; no hay escrituras ni exposición de secretos.
4. Navegación, filtros, estados vacíos y errores son utilizables en escritorio y móvil.
5. Pruebas HTTP y controles estáticos identifican versión y límites; no sustituyen revisión en navegador.
