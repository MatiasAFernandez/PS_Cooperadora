# Administración de formularios y reportes

Corte local del 10/11/2026, base a8108fd, rama
feat/77-administracion-formularios-reportes. Ver [SPEC-021](../specs/021-matias-administracion-formularios-reportes.md) para comportamiento,
diccionario de métricas y límites. No acredita validación institucional.

## Acceso

La cuenta local solicitada se llama admin. Su contraseña se fijó directamente
en la base local y no se versiona. Se autentica por el mismo acceso local de demo;
no necesita staff ni superusuario. No usar esta identidad de demo como identidad
institucional sin la preparación correspondiente.

Para preparar un administrador en otra base de demo:

```powershell
python manage.py migrate
python manage.py preparar_administrador --username admin
python manage.py changepassword admin
```

El comando de preparación no cambia contraseñas existentes; una cuenta nueva
queda sin contraseña utilizable hasta asignarla. La gestión de roles no se ofrece
como editor de permisos global en esta entrega.

## Configuración

Abrir Gestión → Configuración y elegir Gastos o Facturación. En Gastos,
desplegar Catálogos y parámetros para Centros de costo y ATP.

Editar permite cambiar nombre y leyenda del campo y, cuando corresponde,
obligatoriedad, opciones y visibilidad. Los campos esenciales se identifican como
protegidos. Agregar campo o sección permite respuestas de texto, casillas,
botones de opción, listas y adjuntos. Los adicionales aparecen al final, en el
orden configurado. Desmarcar Visible retira el campo sin eliminar sus datos.

Las opciones usan código | texto, una por línea. Para corregir una etiqueta,
conservar el código. Una opción retirada deja de admitirse en nuevas respuestas,
pero los datos previos conservan su etiqueta registrada. Las opciones que
controlan transiciones de negocio mantienen sus códigos.

Después de guardar, abrir nuevamente el formulario de solicitud. Un formulario
abierto antes de un cambio puede solicitar recarga para evitar enviar respuestas
contra otra versión. Las respuestas adicionales se consultan en el detalle con
su historial; sus archivos conservan descarga autorizada por trámite.

## Reportes

Gestión → Reporte ofrece Gastos y Facturación. Gastos conserva el reporte
directivo existente. Facturación permite elegir año, cuatrimestre o trimestre y orden de los
grupos. La explicación de población y fórmulas está disponible en la pantalla.

Facturado neto y cobrado confirmado son medidas distintas. El período identifica
la fecha de presentación de las solicitudes, no la fecha de cada movimiento.
No representa contabilidad, flujo de caja ni proyección de períodos futuros.

Las pestañas aparecen antes del título. En Facturación, elegir año, orden o un
botón de año completo/cuatrimestre/trimestre actualiza el reporte automáticamente.
El resumen indica las fechas incluidas por presentación local. Cambiar el período
conserva año y orden. Evolución separa cantidades e importes y muestra
cuatrimestres para el año completo o meses para cortes más cortos. Las cifras
exactas están en Ver cifras por período. Demanda por grupo muestra el ranking y
las tablas completas por centro o correo. Seguimiento operativo muestra las
acciones pendientes por responsable, su antigüedad y los saldos por confirmar
y excedentes de trámites abiertos con factura. En Gastos también se aplican
las selecciones automáticamente.
Limpiar filtros vuelve al año actual y los criterios iniciales; sin JavaScript,
usar Actualizar reporte.

## Verificación y límites

Se verifican autenticación de la cuenta local, permisos por capacidad/objeto,
campos requeridos, catálogos, conservación de respuestas y adjuntos, cálculos
decimales y regresión de los circuitos. Los resultados ejecutados se detallan abajo. No publicar contraseñas, base ni archivos
reales como evidencia. La validación institucional y la publicación remota se
siguen por separado.


### Resultado del corte

- Suite completa: **908 aprobadas y 1 omitida**, 360,07 s. La omisión corresponde
  al módulo de navegador de gastos, que requiere Playwright no instalado localmente.
- Regresiones focales tras los ajustes finales: **63 aprobadas** (gestión y
  transferencia de gastos) y **57 aprobadas** (gestión, alta de facturación y
  comprobantes). Los conjuntos se solapan y no se suman como casos distintos.
  Cubren tipos de respuesta, retiro/versiones, catálogos históricos, metadatos
  protegidos, compensación de adjuntos, correcciones y el bloque bancario opcional.
  También verifican las etiquetas configuradas en el detalle de facturación.
- Django check, consistencia de migraciones y Ruff sin errores.
- Vistas sintéticas de Configuración, editor y Reporte de facturación revisadas
  en navegador a 1366×900 y 390×844, sin desborde horizontal. El menú de Gestión
  contiene sólo Reporte y Configuración. Se comprobaron pestañas, integración de
  Centros de costo/ATP y controles del editor que dependen del tipo elegido.
- Cuenta local admin preparada y autenticación comprobada; comprobación adicional
  de acceso a Configuración de ambos circuitos y a los dos reportes: HTTP 200.
  Las credenciales no se copiaron a código, documentación ni fixtures.
- Migraciones documentos 0011/0012 y gestión 0001–0003 aplicadas localmente.
  Entorno de prueba: PostgreSQL 18 temporal separado de la base de desarrollo.
- La PR vinculada a #77 y #30 identifica la versión publicada y su estado de
  integración. La revisión de interfaces por el compañero y la validación
  institucional se mantienen separadas de estas pruebas técnicas.

### Verificación de los filtros de Reporte

Ajuste sobre la versión 76567e8, en `codex/30-filtros-reporte-facturacion`:
41 pruebas focalizadas de gestión y reporte de gastos aprobadas. Tras el ajuste
final de distribución, las 9 pruebas de períodos y presentación volvieron a pasar;
están incluidas en las 41 anteriores. Ruff, Django check y diff sin errores.
Revisión con cuenta sintética en PostgreSQL aislado, a 1366×900 y 390×844:
pestañas antes del título, selección automática de año/orden/modalidad, cambio
entre trimestre/cuatrimestre conservando año/orden y limpieza a los valores
iniciales. Sin desplazamiento horizontal en móvil. No requiere migraciones.
