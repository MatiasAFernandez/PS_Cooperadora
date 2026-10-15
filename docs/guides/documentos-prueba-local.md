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
una `MEDIA_URL` para estos archivos. `DOCUMENT_MAX_BYTES` permite ajustar el
límite; este corte interpreta los 10 MB comunicados en D05 como `10000000`
bytes. Se aceptan PDF, JPEG y PNG con extensión y firma concordantes.

Las capacidades sintéticas son independientes: los grupos
`demo_documentos_aporte`, `demo_documentos_metadatos` y
`demo_documentos_descarga` habilitan incorporar, leer metadatos y descargar,
respectivamente. Además, el usuario debe poder ver el trámite mediante las
capacidades de su módulo. Son grupos de prueba, sin asignación institucional.

## Recorrido

Con una sesión de demo que tenga `demo_solicitante` y los tres grupos anteriores,
crear una solicitud de gastos y enviar un PDF ficticio por `POST` multipart a
`/documentos/gastos/<id>/` con campos `archivo`, `tipo=respaldo` y
`procedencia=solicitante`, incluyendo CSRF. La respuesta 201 contiene el ID y
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
incorporación y no deja metadatos utilizables. La elección del almacenamiento
institucional, la regla de documentos requeridos por etapa y la revisión
documental corresponden a decisiones e Issues posteriores.
