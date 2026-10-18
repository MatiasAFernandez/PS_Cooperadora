# Historial y navegación comunes de trámites

Este corte reúne la lectura cronológica de gastos y facturación y ofrece enlaces
a cada circuito según las capacidades del actor autenticado. Los eventos se
proyectan a `EventoHistorialDTO`; los modelos, servicios y reglas de cada
circuito siguen siendo independientes.

## Historial

- El detalle de gastos se obtiene primero desde `visible_expenses(actor)`. Sólo
  entonces se consultan y adaptan las decisiones. La consulta de pago vuelve a
  aplicar la visibilidad y entrega únicamente los campos informativos admitidos;
  el evento de pago se incorpora sólo si esa consulta devuelve un pago.
- Cada DTO identifica el trámite con `gastos:<número>` o
  `facturacion:<número>`. El número público puede coincidir entre circuitos; el
  prefijo distingue su identidad.
- Las decisiones conservan actor, hora fijada por el servidor, estado anterior,
  estado resultante y motivo. Los pagos conservan actor, hora autoritativa de
  registro, importe, moneda, fecha del hecho y referencia externa. Su estado
  resultante es el estado del gasto al registrarse; el pago no cambia ese estado.
- El DTO de decisiones/pagos no expone referencia documental opaca, huella de
  idempotencia ni metadatos privados. Un pago o una decisión no representa una
  revisión documental.
- #24 agrega el hecho `revision_documental` desde `RevisionDocumento` al mismo
  `EventoHistorialDTO`. Conserva resultado, motivo, actor y fecha por versión;
  se consulta en la pantalla autorizada del documento y reutiliza el parcial
  común. Su resultado documental se rotula por separado del estado del trámite.
- La rama local #49 extiende la cronología del detalle de gastos con eventos
  `aporte_documental` y revisiones para actores con
  `documentos.consultar_metadatos`, ordenados por fecha y sin exposición a
  actores que carecen de esa capacidad. #49 permanece local y su prueba
  PostgreSQL aún no se ejecutó.
- `templates/comunes/historial_eventos.html` consume el DTO en ambos detalles.
  La cronología se ordena por hora del evento y usa el identificador del evento
  para desempatar.
- El acceso directo a un objeto continúa sujeto a los filtros de visibilidad del
  servidor. Un enlace o una capacidad de navegación no sustituye las
  comprobaciones por objeto; observar y corregir siguen dependiendo de su
  permiso y de las condiciones del trámite.

## Navegación

`templates/comunes/navegacion_tramites.html` se incluye en las bases de gastos y
facturación y en el inicio autenticado de la demo. Muestra:

| Enlace | Capacidades requeridas |
| --- | --- |
| Consultar gastos | `gastos.consultar_propias` o `gastos.consultar_todas` |
| Presentar gasto | `gastos.presentar` |
| Consultar facturación | `facturacion.consultar_propias` o `facturacion.consultar_todas` |
| Presentar facturación | `facturacion.presentar` |

La navegación no presenta enlaces a acciones por objeto ni a rutas pendientes.
La ausencia del enlace no cambia el comportamiento de las vistas o servicios.

## Alcance y límites

Se comparte la proyección y presentación de hechos, incluidos los de revisión,
sin unificar estados ni transiciones de los circuitos. El historial es de lectura.
La referencia externa del pago se muestra como parte del hecho de pago ya
consultable; la referencia documental no se presenta. La facturación conserva
sus eventos existentes. Aceptar, observar o rechazar un documento no cierra pagos,
deudas ni trámites. El [recorrido de revisión](recorrido-facturacion-i2.md)
explica acceso, permisos e historial por versión.

Las plantillas y pruebas automatizadas acreditan el contrato de presentación,
pero no una aprobación documental, una verificación de cobro ni aceptación de
usuarios. Las pruebas de integración requieren PostgreSQL aislado; no se deben
ejecutar contra una instancia compartida.
