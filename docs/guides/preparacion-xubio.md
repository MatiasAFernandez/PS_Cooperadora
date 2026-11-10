# Preparación para referencias e integración futura con Xubio

Versión v3 (referencias manuales y trazabilidad de correo) — 10/11/2026. Base inspeccionada: `cdd3c29`
(`main`, PR #103). Vinculada a [#84](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/84)
y [#76](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/76).
Responsable de facturación: Matías Alejandro Fernández; Franco Damián Sánchez
conserva gastos/pagos y revisa sus interfaces compartidas.

## Resultado y alcance

La demo pide evitar el archivo duplicado de la factura que ya existe en Xubio,
conservar datos para encontrarla y distinguir emisión, registro y envío. Ver la
[síntesis de la demo](../evidence/demo-2026-10-29.md), tramos 22:25–27:09 y
27:40–29:15. La mención de JSON fue una posibilidad a investigar, no una exportación
comprobada. Las dos transcripciones locales corresponden al mismo audio.

El encargo inicial del 10/11/2026 dejó la API fuera del alcance académico y
preparó documentación y contratos. El encargo posterior autorizó implementar
el registro manual con PDF opcional. El [contrato propuesto](../contracts/referencias-xubio.md)
define la referencia manual sin PDF y su efecto sobre cierre. Ese tramo se
implementa con la migración 0023; la API continúa fuera del alcance. No se agregan
adaptadores HTTP, dependencias ni credenciales.

La opción recomendada es completar primero la referencia manual de #76. Luego
Sistemas podrá agregar lectura asistida de Xubio, reutilizando las mismas reglas
locales. Eso reduce transcripción sin introducir emisión fiscal, sincronización
continua ni infraestructura de colas sin una necesidad acordada.

## Fuentes examinadas y fuerza de la evidencia

Las fuentes originales permanecen en `docs/fuentes/`, ignorado por Git. Este
documento conserva estructura técnica y resultados, sin publicar audio ni datos
operativos. Los nombres relativos permiten encontrarlas sin depender de rutas de
una computadora.

| Fuente local | Comprobación | Límite |
|---|---|---|
| `Demo/transcripcion demo 1.md` y acta enlazada | Solicitan trazabilidad y evitar duplicar archivos; carga posterior a operar externamente. | No confirman todos los campos mínimos, reglas fiscales ni capacidades de API. |
| `Xubio/Xubio Documentation API.mhtml` | Captura del 03/11/2026, 22:38:38 UTC; documentación API 1.1 con autenticación y recursos. | Es documentación, no respuesta de la empresa ni prueba de acceso/licencia. |
| `Xubio/Factura.csv` | 271 bytes, UTF-8 compatible, separador `;`, **una fila de 19 encabezados y cero registros**. | No prueba valores, formatos, exportación por lote ni datos suficientes para importar. |
| `Xubio/Presupuesto.csv` | 154 bytes, UTF-8 compatible, separador `;`, **una fila de 12 encabezados y cero registros**. | No prueba contenido ni equivalencia con comprobantes fiscales o presupuestos de gastos. |

SHA-256 de las fuentes técnicas inspeccionadas:

```text
Factura.csv       b59ce9e10641194061942e5f467b2d26a0133dd027d9422339e99bfbe46668e2
Presupuesto.csv   dfb464e955102b73fa9bf13a1c7421666009e4ae18dfcdea929dc7234bde6685
API.mhtml         f97d461e3654edbeae01397b11131689e0f2adaa82815b8859c6a1c80d6c7f9f
```

La [documentación pública de Xubio](https://xubio.com/API/documentation/index.html)
se consultó el 10/11/2026 para contrastar la autenticación. Recursos y esquemas de
abajo se leyeron de la captura local. Sistemas debe comprobar su vigencia y las
condiciones de su licencia antes de implementar. No se usó «Pruébalo», no se
solicitaron tokens y no se consultaron empresas ni comprobantes reales.

## Correspondencia de las plantillas CSV

| Encabezado de Factura | Correspondencia candidata / precaución |
|---|---|
| `NUMERODOCUMENTO` | Identificación visible; falta una fila para verificar separación de letra, punto de venta y número. No es un ID API demostrado. |
| `TIPOFACTURA` | Tipo/letra por verificar con catálogo y muestra; no asumir que usa los códigos de la API. |
| `FECHA` | Candidata a fecha de emisión; formato y significado por comprobar. |
| `IMPORTETOTAL` | Candidato a importe del comprobante, decimal exacto; separadores y moneda por verificar. |
| `ORGANIZACIONNOMBRE` | Nombre externo candidato del receptor; no identifica unívocamente persona, CUIT ni solicitud. |
| `MONEDA`, `COTIZACION`, `IMPORTEMONPRINCIPAL` | Validar ARS. El sistema no convierte moneda; importe en moneda principal no sustituye automáticamente el total. |
| `DESCRIPCION` | Texto informativo; no usar para asociar automáticamente una solicitud. |
| `IMPORTEGRAVADO`, `IMPORTEIMPUESTOS` | Desglose informativo; no implementar cálculo fiscal local a partir de estas columnas. |
| `VISTAPREVIA`, `DESCMENSAJEESTADO`, `COMPROBANTEELECTRONICO`, `OBTUVOCAE` | Columnas de vista/estado sin valores ni semántica comprobados. No constituyen PDF, URL segura, CAE validado o prueba de envío/cobro. |
| `LISTAPRECIO`, `FECHAVENCIMIENTO`, `PROVINCIANOMBRE`, `VENDEDORNOMBRE` | Información adicional sin necesidad para el registro mínimo propuesto. No derivar permisos, solicitante ni envío de ellas. |

Presupuesto comparte `FECHA`, `DESCRIPCION`, `ORGANIZACIONNOMBRE`,
`IMPORTEGRAVADO`, `IMPORTEIMPUESTOS`, `IMPORTETOTAL`, `MONEDA`,
`FECHAVENCIMIENTO`, `COTIZACION` e `IMPORTEMONPRINCIPAL`. Agrega `DOCUMENTO`
y `ESTADO`; no incluye `NUMERODOCUMENTO` ni `TIPOFACTURA`. El significado y los
valores de esas dos columnas también quedan por verificar.

Ninguna plantilla contiene explícitamente solicitud local, CUIT del emisor,
CUIT del receptor, ID de empresa/recurso Xubio, fecha/destinatario de envío ni
actor local. La letra y punto de venta podrían estar en el número o tipo, pero
**no se puede comprobar con encabezados**. No alcanza para un importador automático
fiable. Una tarea posterior necesitará una muestra sintética representativa,
reglas de formato/duplicados y vista previa para completar lo que falte. No se
incluye un importador CSV en esta entrega.

## Conexión documentada, sin implementación

La fuente describe OAuth2 con `client_credentials`: alta de App Cliente de la
empresa; `POST https://xubio.com/API/1.1/TokenEndpoint`, autenticación HTTP Basic
con Client-ID/Secret-ID y cuerpo form-urlencoded `grant_type=client_credentials`.
El token se usa en `Authorization: Bearer …`. La documentación indica 3600 segundos
y renovación ante `invalid_token`; la implementación futura debe respetar
`expires_in` de la respuesta. No se trata de SSO ni del login institucional.

| Método/recurso bajo `https://xubio.com/API/1.1` | Uso futuro candidato |
|---|---|
| `GET /comprobanteVentaBean` | Buscar comprobantes de venta. Documenta filtros `fechaDesde`/`fechaHasta`; no asumir filtro servidor por CUIT si no se verifica. |
| `GET /comprobanteVentaBean/{id}` | Obtener el detalle seleccionado. El parámetro es ID técnico, no el número fiscal visible. |
| `GET /presupuestoBean` y `GET /presupuestoBean/{id}` | Consultar presupuestos de venta, sólo si se solicita ese alcance por separado. |

El listado de ventas documenta `minimalVersion: true`, `lastTransactionID` y
`limit` como encabezados; los dos últimos sólo para esa versión mínima. No
trasladar paginación de otros recursos a éste ni asumir orden, tamaño máximo,
completitud o idénticos campos del detalle. Presupuestos figura sin parámetros
en la captura. Cuotas, límites y semántica de errores requieren verificación.

La documentación también incluye operaciones de creación, actualización y borrado.
No son necesarias para leer una factura existente y quedan fuera de esta propuesta.
La futura conexión comienza por lectura; sólo el endpoint de token requiere POST.

### Mapeo candidato de respuesta de venta

Los nombres respetan la captura; no son un esquema probado contra una cuenta.

| Campo API | Destino o comprobación local |
|---|---|
| `transaccionid` | Candidato a ID técnico del recurso; confirmar que corresponde al `{id}` consultado. No confundir con IDs de ítems. |
| `externalId` | Campo distinto, semántica no confirmada; no asumir que es nuestra solicitud o clave de idempotencia. |
| `tipo` | La documentación enumera 1=Factura, 2=Nota de Débito, 3=Nota de Crédito, 4=Recibo, 5=Informe Diario. Sólo 1/2/3 se mapean a los tipos locales actuales. |
| `numeroDocumento`, `puntoVenta` | Completar número fiscal y letra sólo con regla confirmada; `puntoVenta` es objeto con IDs/nombre/código, su ID no equivale al número fiscal. |
| `fecha`, `importetotal` | Candidatos a fecha de emisión e importe; validar formato, precisión, moneda y límites locales. `importeMonPrincipal` no prueba por sí solo ARS. |
| `cliente` | Objeto con ID/nombre/código; no aporta explícitamente CUIT en este ejemplo. Buscar/completar receptor autorizado y confirmar la asociación local. |
| `comprobante`, `comprobanteAsociado` | Números de semántica por verificar. No asociar notas automáticamente sólo por estos nombres. |
| `CAE`, `mailEstado` | Datos externos informativos; no prueban revisión local, cobro, destinatario ni fecha de envío efectiva. |
| `descripcion`, ítems y `transaccionCobranzaItems` | No crear solicitudes ni confirmar cobros desde estas estructuras. La verificación local de ingresos sigue separada. |

CUIT del emisor, letra, moneda de la operación y vínculo entre nota/factura
requieren configuración confiable, consultas adicionales o confirmación humana.
La captura no demuestra un PDF descargable ni un enlace profundo estable para
abrir una factura: no inventar URL a partir del ID ni descargar desde `VISTAPREVIA`.

## Punto de extensión para Sistemas

El límite propuesto es **consulta externa → candidato normalizado → confirmación
del operador → servicio local de registro**. Manual, CSV eventual y API eventual
usan el mismo servicio de negocio y las mismas validaciones. No se propone un
registro genérico de proveedores ni modificar `documentos` para hablar HTTP.

Al implementar, ubicar transporte/autenticación/mapeo en un módulo separado de
facturación (por ejemplo `facturacion/integraciones/xubio.py`, inexistente hoy).
Entrada de consulta: configuración de empresa y recurso/ID o filtros verificados.
Salida: candidato con origen, identificación técnica, campos fiscales disponibles
y campos pendientes; nunca un objeto persistido ni un cobro confirmado. La
solicitud destino se elige explícitamente con autorización por objeto, y el
servicio revalida permisos al confirmar. Los candidatos incompletos pueden
completarse manualmente, sin inventar identidad, importe o moneda.

Secretos y token permanecen en servidor, mediante configuración gestionada por
Sistemas, fuera de Git, HTML, URLs e historial. La empresa asociada a la App debe
coincidir con el emisor configurado. Limitar destino HTTP a Xubio por configuración
confiable, con TLS, tiempo de espera y tamaño de respuesta acotados. No aceptar
URLs externas arbitrarias desde CSV/formularios. Usar decimales exactos al mapear
JSON monetario; no pasar por `float`.

Ante token inválido, renovar y reintentar lectura una vez; credenciales denegadas,
timeout, cuota, recurso inexistente o respuesta incompatible producen un error
acotado sin persistir un candidato parcial ni registrar envío/revisión. No
sobrescribir un registro local cuando cambie el dato externo. La operación manual
permanece disponible sin credenciales o durante una caída de Xubio. No mantener
transacciones SQL abiertas durante HTTP ni consultar Xubio al evaluar el cierre.

## Trabajo posterior y puntos concretos del repositorio

El tramo manual de #76 adapta las piezas siguientes; la tabla conserva los
puntos inspeccionados durante la preparación para facilitar su mantenimiento:

| Pieza actual | Adaptación necesaria antes de habilitar referencias sin PDF |
|---|---|
| `facturacion/models.py`, `ComprobanteExterno.documento` | OneToOne anulable desde 0023. Ausencia sólo para Xubio, manteniendo unicidad, sucesores y vínculos históricos. |
| `facturacion/forms_comprobantes.py`, `comprobantes.py` y `views_comprobantes.py` | Alta/corrección condicionales y permisos de bytes; evitar copiar o revisar un archivo ausente. |
| `facturacion/seguimiento.py`, `models_cierre.py` | Diagnóstico, respaldo opcional, primer adjunto real, huella y resolución coherentes. `ActualizacionRespaldo` exige `anterior` y `nuevo`. |
| `facturacion/atencion.py`, consultas, exportación y plantillas de facturación | Pendientes/acciones, detalle, historial y PDF de solicitud sin asumir documento presente. Reutilizar componentes y verificar escritorio/móvil según la guía visual. |
| Migraciones `0007`, `0011`, `0013`, `0016`–`0022` de facturación | Leer la evolución de funciones/triggers; nueva migración hacia adelante para las guardas efectivas de comprobante, actualización y resolución. No editar migraciones aplicadas ni retirar protecciones globales. |
| `documentos` y consumidor C01 de gastos | Conservar contrato y validaciones; ninguna dispensa general de archivos o revisión. |

Después, si Sistemas decide conectar, debe confirmar licencia/empresa/credenciales,
esquemas vigentes, identificación fiscal, moneda, límites/paginación, asociación
de notas y acceso de prueba autorizado. Implementar transporte y mapeo separados;
mostrar candidato y confirmar asociación a la solicitud antes de usar el servicio
local. La clave externa empresa + recurso + ID complementa la unicidad fiscal;
una factura ya cargada manualmente se enlaza sin duplicarla. No se agregan tareas
programadas, webhooks, envío, emisión ni escritura en Xubio sin otro alcance.

Una eventual implementación deberá probar el mapeo con respuestas sintéticas,
renovación de token, errores/timeout, paginación, moneda no admitida, candidatos
incompletos y duplicados frente a la carga manual. Las pruebas contra una empresa
de Xubio corresponderán a Sistemas cuando autorice la conexión y disponga de un
entorno apropiado; no son necesarias ni se ejecutan para esta preparación.

## Verificación de esta entrega y límites

Se inspeccionaron fuentes locales, issues #76/#84, contratos, modelos, servicios,
formularios y guardas SQL sobre la base indicada. Se contrastaron columnas,
encabezados, tamaños y huellas; se revisaron enlaces relativos y diff documental.
Los escenarios del contrato son la aceptación para una implementación posterior.

La preparación v1 no ejecutó pruebas. El corte v2 agrega pruebas de registro
sin PDF y regresión Django sobre PostgreSQL temporal aislado. No se ejecutan
pruebas de API, autenticación externa ni importación. No hay
evidencia de acceso a la licencia, exportación con filas, formatos de datos o
correspondencia completa con el modelo local. Este paquete no cierra #76/#84,
no valida H1–H4 ni nuevas políticas institucionales.
Las decisiones y estados operativos se mantienen en las issues.

## Uso del registro manual sin PDF

Aplicar `python manage.py migrate` antes de iniciar la versión nueva. En
«Registrar factura o nota externa», el campo «PDF del comprobante (opcional para
Xubio)» y un aviso visible explican que basta con registrar los datos. Para Otro
origen sigue siendo obligatorio. La conformidad del PDF sólo se ofrece cuando
se selecciona un archivo. El detalle sin archivo no presenta descarga ni revisión
inexistentes. Desde «Modificar comprobante externo» puede adjuntarse el primer
PDF, con motivo e historial; ese archivo queda pendiente de revisión.

No se ha conectado Xubio ni implementado envío automático de correo. El registro
por sí solo no afirma que se haya enviado una factura ni verifica un ingreso.

### Verificación histórica del corte sin PDF (v2)

Base `cdd3c29` más cambios de `feat/76-xubio-pdf-opcional` en ese corte local.
Migración `facturacion.0023_comprobante_xubio_pdf_opcional` aplicada correctamente
en la base local. La base temporal de pruebas se mantuvo aislada y se detuvo
al terminar.

- Regresión de `tests/facturacion` y revisión documental de integración: **240
  pruebas aprobadas**. Después de completar los casos de primer adjunto y HTTP,
  se ejecutaron los **6 casos finales** de `test_xubio_sin_pdf.py`: todos aprobados.
  Estos seis incluyen casos ya presentes en la ejecución ampliada; no se suman
  como pruebas distintas.
- PostgreSQL 18 temporal, datos sintéticos; sin modificar permisos de la base
  de desarrollo, cuyo usuario no puede crear bases de prueba.
- Django check, consistencia de migraciones, Ruff y diff sin errores.
- Formulario renderizado por Django con datos sintéticos inspeccionado en
  navegador a 1366×900 y 390×844. Aviso visible, campo opcional para Xubio,
  exigencia dinámica al seleccionar Otro y sin desborde horizontal en móvil.
  Las escrituras HTTP se comprobaron con el cliente de pruebas; la inspección
  visual utilizó una copia temporal del HTML con los estilos/scripts reales.
- No se ejecutó la suite global de gastos ni pruebas contra Xubio. La API permanece fuera del alcance.

## Envío declarado y recepción opcional (0024)

En el alta, marcar «Ya envié este comprobante por correo» despliega destinatario
precargado y fecha de hoy, editables. Sin marcarlo, no agrega requisitos. Se valida
correo y fecha no futura ni anterior a emisión; guardar el comprobante y el envío
es una sola transacción. El formulario no envía correos.

En el detalle, «Informar envío por correo» permite declararlo después. Si existe,
la sección permite informar otro envío o corregir sus datos sin borrar el anterior.
El último envío se muestra con fecha y destinatario; todos quedan en historial.
El titular ve «Confirmar que recibí este comprobante» y puede pulsarlo una vez,
incluso con la solicitud cerrada. Es voluntario, no genera recordatorios ni
bloquea el cierre. Las confirmaciones anteriores no se trasladan a otro envío
o a una versión corregida del comprobante.

Aplicar `python manage.py migrate` para incorporar 0023 y 0024 antes de iniciar
la versión. Las migraciones no inventan envíos ni acuses históricos. Con hechos
registrados, las reversas se rechazan para preservar trazabilidad; corregir hacia
adelante. Mantener copias de base y archivos según la guía de recuperación vigente.

### Verificación final de referencias y correo (v3)

Corte de entrega: base `cdd3c29`, rama `feat/76-xubio-pdf-opcional`, migraciones
0023/0024. El SHA publicado y el resultado de integración se consultan en la PR
vinculada a #76; la validación institucional continúa separada.

- Suite completa: **889 aprobadas y 1 omitida**, 363,65 s. La omisión corresponde
  al módulo de navegador de gastos por ausencia de Playwright en el entorno local.
- Tras ajustar el formato ISO de la fecha precargada y las etiquetas del historial,
  regresión focal final: **15 aprobadas** (`test_envios.py` e historial común).
- Django check, `makemigrations --check --dry-run`, Ruff y revisión del diff correctos.
- Entorno local: Python 3.14 y PostgreSQL 18 temporal aislado; CI usa Python 3.11
  y PostgreSQL 17, por lo que su resultado se informa por separado en la PR.
- Formulario y detalle sintéticos revisados en navegador a 1366×900 y 390×844,
  con componentes existentes. Al marcar envío aparecen destinatario y fecha de
  hoy; se verificó la fecha ISO real del control y ausencia de desborde horizontal.
  Se corrigió el formato de fecha detectado durante esta comprobación.
- Permisos por titular/objeto, POST/CSRF, reintentos, conservación de hechos,
  rollback de comprobante/envío y acuse posterior al cierre cubiertos con pruebas.
  No se enviaron correos ni se consultó la API de Xubio.
