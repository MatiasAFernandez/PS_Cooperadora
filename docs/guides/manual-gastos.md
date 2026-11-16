# Manual de usuario del módulo de Gastos

> **Estado del documento:** borrador de trabajo sobre el comportamiento integrado de Gastos. El capítulo de cierre explícito se completará una vez integrado el corte correspondiente.

Este manual describe cómo operar el circuito de **Gastos** en la plataforma de Cooperadora, desde la presentación de una solicitud hasta el registro del pago, la rendición documental y la consulta de reportes y avisos.

---

## 1. Acceso y roles en el circuito

Para ingresar al sistema con tu usuario y contraseña o mediante el acceso de demostración, seguí los pasos de la [guía de acceso local](acceso-local.md). La asignación de perfiles y cuentas se detalla en la [guía de identidad y perfiles](identidad-demo-local.md).

Según las tareas habilitadas para tu perfil, podés participar en el circuito como:

- **Solicitante:** presenta nuevas solicitudes, corrige solicitudes observadas, informa o actualiza datos de transferencia antes del pago y adjunta o reemplaza respaldos documentales.
- **Operación de evaluación:** revisa solicitudes presentadas o postergadas para aceptarlas, observarlas, postergarlas o rechazarlas.
- **Registro de pagos:** carga el registro de pagos externos ya efectuados, incorpora comprobantes bancarios y constancias de retención ATP, y rectifica datos del pago cuando corresponde.
- **Revisión documental:** evalúa los archivos adjuntos (facturas, presupuestos, comprobantes y constancias) registrando si quedan aceptados, observados o rechazados.
- **Consulta o administración:** consulta bandejas, historial y reportes, o administra catálogos de centros de costo y parámetros de control.

---

## 2. Modalidades: compra directa vs. reintegro

Al presentar un gasto debés elegir una modalidad operativa que determina cómo se respalda y se rinde el trámite:

- **Compra directa:** Cooperadora abona directamente al proveedor. Para iniciar o registrar el pago podés presentar un **presupuesto o proforma**, pero después del pago debés incorporar la **factura definitiva del proveedor** dentro del plazo de gracia para no generar mora documental.
- **Reintegro:** abonás primero el gasto y Cooperadora te reintegra el importe. Para poder registrar el pago es obligatorio contar previamente con una **factura de proveedor** incorporada al trámite.

---

## 3. Presentar una solicitud y cargar respaldo

1. En la barra de navegación, seleccioná **Presentar gasto** para abrir **Presentar solicitud de gasto**.
2. Completá los campos principales:
   - **Concepto** del gasto.
   - **Monto estimado** en pesos argentinos (formato `es-AR`, por ejemplo `1250,50`). Al salir del campo, un importe válido se formatea automáticamente; si el valor es inválido, el campo conserva el texto para que lo corrijas.
   - **Modalidad** (*Compra directa* o *Reintegro*), **Centro de costo** (opcional, tomado del catálogo activo) y **Unidad requirente**.
3. Si deseás adelantar los **Datos de transferencia** (CUIT/CUIL, CBU o alias y correo para el comprobante), podés completarlos en el bloque desplegable antes de enviar; también podrás editarlos más adelante mientras la solicitud no esté rechazada ni pagada.
4. En la sección de respaldo podés adjuntar el archivo inicial (PDF o imagen permitida según el tipo de documento).
5. Hacé clic en **Enviar Solicitud**.

> **Importante:** si tenés compras directas pagadas con factura definitiva pendiente, el sistema muestra el seguimiento documental. Cuando superás el límite de trámites en mora configurado, la presentación queda bloqueada hasta regularizar los comprobantes. La pantalla indica el plazo y el límite vigentes.

---

## 4. Evaluación de solicitudes

Quien evalúa el trámite accede desde la bandeja **Solicitudes de gasto** (donde puede activar el filtro **Requieren atención** o **Filtrar pendientes**) y abre el detalle de la solicitud. Desde **Presentada** puede aceptar, observar, postergar o rechazar. Desde **Postergada** puede aceptar, observar o rechazar:

- **Aceptar:** habilita el trámite para continuar hacia el registro del pago. El motivo es opcional.
- **Observar:** devuelve el trámite al solicitante en estado **Observada** para que corrija datos principales y lo reenvíe. **Exige motivo obligatorio**. Mientras está observada, no se pueden registrar nuevas decisiones operadoras hasta que el titular subsane.
- **Postergar:** deja el trámite en espera en estado **Postergada** por decisión operativa (por ejemplo, falta de disponibilidad o prioridad), sin devolverlo como observación editable al titular. **Exige motivo obligatorio**.
- **Rechazar:** da por denegada la solicitud en forma definitiva y bloquea pagos, ediciones de datos de transferencia y nuevos aportes documentales desde las pantallas de Gastos. **Exige motivo obligatorio**.

---

## 5. Corregir y reenviar una solicitud observada

Si una solicitud tuya recibe el estado **Observada**:

1. Abrí el detalle del trámite: verás el aviso con la fecha y el **Motivo** de la observación vigente.
2. Hacé clic en **Corregir solicitud**.
3. En la pantalla de corrección podrás revisar los datos fijos del trámite (número, modalidad, unidad requirente y estado actual) y modificar únicamente:
   - **Concepto**
   - **Monto estimado** (con validación y formato `es-AR` al salir del campo; ante un valor inválido muestra el aviso junto al campo sin borrar lo que escribiste)
   - **Centro de costo** (se ofrecen los centros activos y, si el trámite ya tenía uno histórico desactivado, se mantiene seleccionable)
4. Hacé clic en **Guardar y reenviar**. El trámite vuelve a estado **Presentada** para nueva evaluación y deja registro en la cronología como **Subsanación de solicitud**.
5. Si necesitás corregir datos bancarios o archivos en lugar de esos tres campos, usá los enlaces a **Datos de transferencia** o **Documentos del trámite**. Si alguien modificó la solicitud mientras estabas editando, verás un aviso de conflicto de versión conservando tus datos en pantalla para que revises antes de reenviar.

---

## 6. Documentos: incorporación, reemplazo y revisión

En la sección documental del detalle (y en la vista dedicada **Documentos del trámite**) se listan todas las versiones de archivos asociadas al gasto:

- **Incorporar o reemplazar:** desde **Cargar o reemplazar respaldo comercial** o desde el botón **Reemplazar** de una versión vigente podés subir una nueva versión en PDF o formato admitido. Cada versión anterior se conserva como historial inmutable y queda vinculada a la nueva.
- **Descargar:** quienes tienen acceso de lectura pueden descargar cada archivo desde el ícono de descarga.
- **Revisar:** quien cumple rol de revisión documental ingresa mediante **Revisar** (o **Ver detalle**) para registrar si la versión queda **Aceptado**, **Observado** (con motivo obligatorio) o **Rechazado** (con motivo obligatorio). La revisión documental es independiente del alta del archivo y del estado de pago.

---

## 7. Registro de pago externo, retención ATP y rectificación

El sistema **no ejecuta transferencias bancarias ni opera con home banking**: registra y audita pagos efectuados por fuera de la aplicación.

1. Sobre una solicitud **Aceptada** sin pago previo, quien registra pagos hace clic en **Registrar pago externo** en el detalle.
2. Si necesita copiar el CBU/alias informado por el solicitante, dispone del botón de copia rápida junto al dato.
3. Completa la **fecha de pago** (puede usar **Hoy**), el **importe bruto**, la **retención ATP** (con apoyo de **Calcular sugerencia** y **Usar este importe** según parámetros vigentes, o ingresando el monto correspondiente), la **referencia bancaria externa** (si existe), el **comprobante bancario en PDF** (obligatorio) y selecciona el **respaldo comercial** vigente compatible con la modalidad.
4. Si la retención ATP es mayor a cero, puede adjuntar la **constancia ATP** en PDF en el mismo acto o dejarla pendiente para cargarla después mediante **Incorporar constancia ATP** desde el detalle del pago.
5. Si luego es necesario corregir importes, fecha, referencias o reemplazar el comprobante bancario, se utiliza **Rectificar pago** indicando un motivo obligatorio. Cada rectificación genera una nueva versión y conserva el detalle antes/después en el historial del pago.

---

## 8. Seguimiento de pendientes y mora documental

Las **compras directas** ya pagadas que aún no cuentan con una **factura de proveedor** vigente (pendiente de revisión o aceptada) permanecen en seguimiento:

- **Plazo de gracia:** se cuenta desde la fecha de pago y depende del parámetro vigente, indicado en el aviso.
- **Aviso preventivo:** el solicitante ve el seguimiento de comprobantes pendientes al ingresar a **Presentar gasto**, con los plazos y el límite aplicables.
- **Bloqueo de nuevas solicitudes:** si las compras directas en mora superan el máximo configurado, la presentación queda bloqueada hasta regularizar los comprobantes desde los enlaces del aviso.
- Los **reintegros** no generan mora posterior porque exigen factura definitiva antes de registrar el pago.

---

## 9. Bandeja, avisos, historial y reportes

- **Bandeja (`Solicitudes de gasto` / `Mis solicitudes`):** permite buscar por número, concepto o unidad, filtrar por estado, modalidad, atención o subsanación, y abrir la vista rápida lateral sin salir del listado.
- **Cronología del trámite:** reúne en orden cronológico las decisiones, subsanaciones, aportes documentales, revisiones y el registro del pago, según los alcances descriptos en la [guía de historial y navegación común](historial-y-navegacion-comunes.md).
- **Avisos web y correo:** el ícono **Avisos** en la barra superior muestra notificaciones de nueva solicitud, cambios de decisión (incluida la observación) y registro inicial de pago; el envío de correo depende de la configuración activa del entorno. Para más detalle, consultá la [guía de avisos web de Gastos](avisos-web-gastos.md).
- **Reporte directivo y catálogos:** el **Reporte Directivo de Gastos** consolida solicitudes, compromisos y pagos con retención ATP por cuatrimestre y centro de costo. Su uso y la gestión de catálogos y parámetros se explican en la [guía de administración y reportes](administracion-formularios-reportes.md).

---

## 10. Cierre explícito del gasto

El cierre administrativo marca que el trámite pagado cuenta con toda su documentación obligatoria verificada y aceptada. El cierre se registra por separado del estado de decisión (**Aceptada** / **Pagada**) y muestra la etiqueta **Cerrada** en la cabecera, en la sección **Cierre administrativo** del detalle y junto a **Pagada** en la bandeja y el panel de vista rápida.

### Requisitos para habilitar el cierre

Un trámite sólo puede cerrarse cuando reúne todas estas condiciones:

- La solicitud está **Aceptada** y tiene un **pago externo registrado**.
- Cuenta con una **factura de proveedor definitiva** vigente y revisada como **Aceptado** (tanto en *Compra directa* como en *Reintegro*; un presupuesto o proforma o un ticket no fiscal no habilitan el cierre).
- El **comprobante bancario** del pago está vigente y revisado como **Aceptado**.
- Si el pago tiene **retención ATP mayor a cero**, la **constancia ATP** está vigente y revisada como **Aceptado**.

### Seguimiento de pendientes y confirmación

1. Mientras falte algún requisito, la sección **Cierre administrativo** del detalle muestra los pendientes concretos con enlaces directos para resolver cada paso según tus permisos (registrar o rectificar el pago, incorporar constancia ATP, cargar respaldo o ir a **Revisar**). Si tu perfil no incluye consulta documental, verás únicamente el estado general (*Pendiente de verificación documental por Cooperadora*), sin nombres de archivos.
2. Cuando todos los documentos obligatorios están aceptados, quien tiene autorización para cerrar y consultar metadatos documentales ve el botón **Cerrar trámite**.
3. Al hacer clic, se abre **Confirmar cierre de solicitud** con el resumen del pago registrado (importes bruto, retención ATP y neto en formato `es-AR`) y los documentos aceptados que respaldarán el cierre.
4. Podés agregar una **Observación de cierre (opcional)** y confirmar con **Confirmar cierre del trámite**, o volver sin cambios con **Cancelar**.
5. Si el trámite, el pago o algún documento cambió mientras estabas en la pantalla de confirmación, el sistema impide el cierre y **conserva la observación que escribiste** para que revises los requisitos actualizados antes de volver a intentar.

### Efectos del cierre

- En la cronología del trámite queda registrado el evento **Cierre del trámite**, sin exponer nombres ni identificadores de archivos a perfiles sin permiso documental.
- El trámite cerrado deja de contarse como pendiente o en mora documental.
- Quedan bloqueadas las operaciones posteriores sobre el trámite: rectificación de pago, incorporación posterior de constancia ATP, carga o reemplazo de respaldos en Gastos y nuevas incorporaciones o revisiones también en las rutas directas de documentos.
