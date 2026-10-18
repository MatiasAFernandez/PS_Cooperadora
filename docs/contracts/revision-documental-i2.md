# Revisión documental — perfil de demo #24

Perfil preparado el 18/10/2026. Matías pidió avanzar con #24 y eligió incorporar
RECHAZADO además de ACEPTADO/OBSERVADO. Son decisiones del perfil técnico de demo;
Franco revisa la interfaz común y su consumidor de gastos. La asignación a cargos
reales y los requisitos documentales por etapa se validan después con Cooperadora.

## Operación y permisos

`documentos.revision.revisar(actor, documento_id, resultado, motivo,
revision_esperada)` registra un hecho sobre una versión exacta. Exige capacidad
independiente `documentos.revisar`, consulta de metadatos y acceso al trámite.
Leer, aportar, decidir o pagar no concede revisión; staff/superusuario no la
otorgan. La descarga conserva su capacidad independiente. Las capacidades se
resuelven en cada petición según el contrato de identidad vigente.

La preparación local `preparar_identidad_demo --facturacion --revision-documental`
asigna explícitamente el grupo `demo_documentos_revision` sólo a demo_o, junto
con metadatos/descarga. Sin la nueva opción no amplía facultades. No asigna pago,
no cambia contraseñas ni quita grupos existentes. Usar únicamente datos sintéticos.

## Resultados e historial

- Sin revisión: **PENDIENTE**, sin inventar actor ni fecha de revisión.
- **ACEPTADO**: conformidad de esa versión; motivo opcional.
- **OBSERVADO** y **RECHAZADO**: motivo obligatorio, hasta 2000 caracteres.

Cada revisión conserva documento, resultado, motivo, actor y hora del servidor.
Un nuevo resultado agrega otro hecho; no altera ni elimina los anteriores.
`RevisionDocumento.como_historial()` adapta ese hecho a EventoHistorialDTO,
con tipo `revision_documental`; el resultado documental no es un estado del
trámite. La pantalla usa el parcial común y escapa nombres y motivos.
El historial autorizado sigue consultable aunque cambie el resultado o se
reemplace el archivo. No se modifica el contenido ni el estado del trámite.

La consulta se autoriza con metadatos y acceso por objeto. Un objeto ajeno o
inexistente devuelve 404; sin capacidad suficiente se deniega con 403. La página
`/documentos/<id>/revision/` permite consultar y, con permiso, registrar por POST
con CSRF. Los respaldos de facturación enlazan esta página. La integración de
la navegación propia de gastos sigue bajo responsabilidad de Franco en #28.

## Concurrencia, reemplazo y atomicidad

El formulario envía el ID de la última revisión vista, o cero si no existe.
El servicio bloquea la raíz documental, compartida con reemplazo y C01; revalida
visibilidad, vigencia y revisión esperada. Una revisión concurrente, un reenvío,
un resultado idéntico sin cambios o una versión reemplazada devuelve conflicto
(409). Una entrada inválida devuelve 400. El cliente debe recargar tras conflicto.

El registro de revisión es el propio hecho de historial: se escribe en una
transacción y un fallo no deja un resultado separado o evento parcial. PostgreSQL
protege resultados y motivos válidos e impide UPDATE/DELETE de revisiones incluso
por SQL directo. Las autorizaciones y la secuencia de revisión pertenecen al
servicio; escribir directamente en tablas no es una API de negocio.

Un reemplazo crea una versión sin revisiones. No hereda aceptación, observación
ni rechazo. La revisión de la versión anterior se conserva; no se permite seguir
revisando la versión reemplazada. Los archivos existentes no se tocan al revisar.

## Pendientes y consumidor C01

`version_aceptada(documento)` sólo informa si la última revisión es ACEPTADO y la
versión sigue vigente. Es una consulta interna sobre un documento ya autorizado;
no determina qué requisito de un circuito satisface ni cierra deudas/trámites.
Un futuro consumidor que tome decisiones debe revalidar dentro de su transacción
bajo el bloqueo de raíz, no confiar en una lectura previa de esta consulta.
Una carga, ausencia de revisión, OBSERVADO o RECHAZADO no acredita conformidad.

El adaptador C01 omite versiones OBSERVADO/RECHAZADO del selector y vuelve a
rechazarlas bajo el bloqueo transaccional. Una revisión no puede intercalarse
durante la verificación de pago hasta el commit/rollback. Se conserva la regla
explícita previa de demo: sin revisión, el respaldo permite el recorrido técnico,
sin afirmar conformidad ni cancelar deuda. El DTO de C01 no cambia. Los pagos
ya registrados no se modifican ni invalidan por una revisión posterior.

Antes de integrar, Franco debe revisar este ajuste del proveedor y su contrato;
#24 no se declara cerrada por implementar o probar esta propuesta. Las reglas
reales por tipo/etapa y los consumidores de cierre corresponden a #27/#28 y a
la validación de Cooperadora en #29.

## Migraciones y reproducción

0007 agrega la tabla sin revisar documentos históricos; 0008 instala las guardas
de auditoría. No se alteran versiones ni archivos. Si ya existen revisiones,
ambas reversas se rechazan para conservar historial y guardas. Sin revisiones
se permite revertir/reaplicar en pruebas; con datos corregir hacia adelante.
Probar con PostgreSQL aislado, migraciones y almacenamiento temporal. La
[evidencia técnica](../evidence/i2-24-revision-documental.md) registra versión,
pruebas ejecutadas y límites.
