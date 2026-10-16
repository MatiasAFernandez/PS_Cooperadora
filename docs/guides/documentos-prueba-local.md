# Documentos protegidos: prueba local de #19

Este primer tramo usa archivos ficticios y el adaptador de identidad de demo.
Implementa el proveedor documental para solicitudes de gastos existentes; el
consumidor de facturación y la integración de ambos circuitos se completan en
#22/#28. No representa una configuración institucional.

## Configuración

Usar PostgreSQL como indica el README y habilitar `DEMO_IDENTITY_ENABLED=true`
solamente en el entorno de prueba. `DOCUMENT_STORAGE_ROOT` define el directorio
privado (por defecto `private_documents` dentro del proyecto); no debe servirse
por el servidor web ni ubicarse bajo `STATIC_ROOT`. La aplicación no registra
una `MEDIA_URL` para estos archivos. `DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES` permite
ajustar el límite; el valor aprobado es `10485760` bytes (10 MiB exactos),
inclusive. Se aceptan PDF, JPEG y PNG con extensión, MIME declarado y firma
concordantes. Los archivos vacíos se rechazan. Véase el
[registro de decisiones](../decisions/0002-documentos-issue-19.md).

Las capacidades sintéticas son independientes: los grupos
`demo_documentos_aporte`, `demo_documentos_metadatos` y
`demo_documentos_descarga` habilitan incorporar, leer metadatos y descargar,
respectivamente, con los códigos `documentos.incorporar`,
`documentos.consultar_metadatos` y `documentos.recuperar_contenido`. Además, el
usuario debe poder ver el trámite mediante las capacidades de su módulo. Son
grupos de prueba, sin asignación institucional. Los códigos previos de lectura
y descarga siguen disponibles como alias para los consumidores de gastos.

## Recorrido

Con una sesión de demo que tenga `demo_solicitante` y los tres grupos anteriores,
crear una solicitud de gastos y enviar un PDF ficticio por `POST` multipart a
`/documentos/gastos/<id>/` con campos `archivo`,
`tipo=FACTURA_PROVEEDOR` y `procedencia=SOLICITANTE`, incluyendo CSRF. La
respuesta 201 contiene el ID y
los metadatos, sin la ruta física. `GET` a esa misma URL lista los documentos;
`GET /documentos/<documento_id>/` devuelve metadatos y
`GET /documentos/<documento_id>/archivo/` descarga el archivo.

Repetir las consultas con otra cuenta solicitante: recibe 404 para el trámite
ajeno y para los identificadores directos. Quitar cada grupo documental por
separado verifica que las capacidades no se sustituyen entre sí. La suite usa
PostgreSQL y un directorio temporal, con archivos sin datos personales:

```powershell
python -m pytest tests/documentos -q
```

Un fallo de escritura o de base limpia el archivo guardado durante la
incorporación y no deja metadatos utilizables. La matriz aprobada establece
tipos, procedencias y cantidades esperadas por circuito; los mínimos por etapa
se verificarán en las operaciones de cada circuito. Facturación aún no puede
incorporar archivos porque falta su modelo y resolver (#22/#28). La elección
del almacenamiento institucional y la revisión documental (#24) siguen
separadas. Una reversión posterior de una transacción exterior requiere un
mecanismo adicional de limpieza antes de integrar incorporaciones anidadas.
