# SPEC-021 — Administración de formularios y reportes por circuito

- Responsable: Matías Alejandro Fernández. Franco Damián Sánchez conserva
  gastos/pagos y revisa los efectos sobre interfaces compartidas.
- Fuentes: pedido del usuario del 10/11/2026; SPEC-014/#77, SPEC-008/#30 y demo
  del 29/10/2026 (08:16–09:57 y 01:48:18–01:54:00).
- Alcance técnico implementado en rama de tarea; validación institucional separada.

## Acuerdo y límites

El usuario solicita una cuenta administradora local con las capacidades de la
operadora, configuración por circuito y reportes separados. Confirmó proteger
los campos esenciales en lugar de redefinir pagos, cobros o cierre.
Las credenciales solicitadas se configuran sólo en la base local; no son parte
de esta especificación, de fixtures ni de migraciones.

El perfil tiene capacidades explícitas de gestión, sin depender de staff o
superusuario. Se conservan los accesos previos de operación a catálogos de gastos
y de lectura global a sus respectivos reportes. El mantenimiento de formularios
requiere capacidad administrativa, también mediante POST directo.

## Formularios

- Cada circuito mantiene su propia revisión de configuración. El administrador
  edita etiquetas y ayudas, retira campos opcionales o adicionales, cambia su
  obligatoriedad y define opciones de respuesta.
- Los campos esenciales conservan presencia y reglas del negocio. Sus textos
  se pueden editar; los códigos de modalidad y condiciones que gobiernan
  operaciones no se pueden retirar ni sustituir por códigos arbitrarios.
- Producto/servicio, condición IVA y centro de costo de facturación admiten
  opciones configuradas, con códigos estables. El centro de costo de gastos
  conserva su catálogo existente, con retiro lógico y referencias históricas.
- Adicionales admitidos: texto, párrafo, selección simple/múltiple, botones de
  opción, casilla, sección explicativa y adjunto. Los botones son controles de
  respuesta; no permiten inyectar JavaScript, SQL ni acciones financieras.
- Los campos del circuito conservan su posición. Los adicionales se ordenan al
  final del formulario; las secciones agrupan la información adicional.
- Retirar significa dejar de ofrecer en nuevas presentaciones, sin borrar
  respuestas ni archivos anteriores. Cada modificación registra autor, fecha y
  esquema; cada presentación/corrección conserva sus respuestas y esquema.
- Una configuración obsoleta se rechaza en servidor. El guardado comprueba
  nuevamente la revisión bajo bloqueo para evitar mezclas entre versiones.
- Los adjuntos reutilizan almacenamiento, autorización por trámite y política
  PDF/JPEG/PNG de hasta 10 MiB. Se clasifican como ANEXO_SOLICITUD: no sustituyen
  facturas, presupuestos comerciales ni comprobantes de cobro/pago.
- La operación documental compensa archivos ante errores. Una corrección de
  facturación conserva el anexo anterior si no se aporta reemplazo. Los cambios
  de campos no convierten solicitudes históricas en pendientes nuevos.

## Reporte de facturación: diccionario técnico

Población: solicitudes operativas presentadas en el año/cuatrimestre local
elegido; se excluyen borradores y anuladas y se informa la cantidad de anuladas.
Se analizan los importes vigentes al consultar de esa población; no se presenta
como movimiento de caja por fecha de cobro.

| Métrica | Fórmula |
|---|---|
| Cantidad | Número de solicitudes de la población. |
| Solicitado | Suma de importes solicitados de la población. |
| Facturado neto | Facturas y débitos vigentes menos créditos vigentes. |
| Cobrado confirmado | Cobros vigentes con resultado CONFIRMADO; pendientes/rechazados/rectificados no cuentan. |
| Solicitud promedio | Solicitado / cantidad de solicitudes. |
| Factura promedio | Suma de facturas vigentes / cantidad de facturas, sin contar notas como nuevas facturas. |

ARS, decimales exactos y promedios redondeados a dos decimales con ROUND_HALF_UP.
Sin población, totales y promedios son cero. Se muestran cuatrimestres, centros
o grupos y correos solicitantes; se puede ordenar grupos por cantidad o importes.
Los correos compartidos no fusionan personas ni alteran titularidad.

El reporte de gastos reutiliza el productor y los controles existentes. No se
consolidan saldos de ambos circuitos ni se importan históricos o proyecta inflación
(SPEC-017 conserva su alcance separado). Este diccionario es un criterio técnico
explícito para este pedido; no se atribuye confirmación institucional de cada fórmula.

## Presentación y navegación

En Gestión aparecen únicamente Reporte y Configuración. Cada sección contiene
pestañas Gastos y Facturación según permisos. Configuración de Gastos incorpora
los mismos formularios de Centros de costo y ATP mediante un parcial reutilizado.
Se mantienen layout, tokens, navegación y componentes existentes, Django y JS
nativo. Escritorio y móvil forman parte de la verificación.

## Aceptación

1. La cuenta administradora autentica localmente y tiene facultades de operadora
   y gestión; las credenciales no aparecen en Git.
2. Un solicitante/lector/operador sin gestión no puede editar por GET o POST.
3. Cambios por circuito se reflejan en el formulario correcto; campos requeridos
   y opciones se validan en servidor, conservando las reglas esenciales.
4. Nuevas respuestas, opciones retiradas y adjuntos mantienen historia y permisos;
   errores de validación/storage o versiones obsoletas no dejan datos parciales.
5. Un reporte sintético coincide con cálculos manuales y distingue importes;
   filtros manipulados no amplían acceso ni producen cifras engañosas.
6. Navegación de Gestión presenta las dos entradas acordadas y pestañas accesibles.

La evidencia ejecutada y sus límites se registran en la guía de administración;
las issues conservan el seguimiento operativo. No incluye excepciones de deuda
de #85 ni nuevas integraciones externas.
