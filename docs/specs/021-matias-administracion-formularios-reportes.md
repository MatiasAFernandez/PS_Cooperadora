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

Población: solicitudes operativas presentadas en el año, cuatrimestre o trimestre local
elegido; se excluyen borradores y anuladas del cálculo.
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
| Mediana de factura | Importe central de las facturas vigentes ordenadas. Si hay dos importes centrales, su promedio. |
| Saldo por confirmar | En cada trámite abierto con factura, la parte positiva de neto menos confirmado. Sumar los saldos de cada trámite. |
| Excedente confirmado | En cada trámite abierto con factura, la parte confirmada por encima del mayor entre el neto y cero. Sumar los excedentes de cada trámite. |

ARS, decimales exactos y promedios y mediana redondeados a dos decimales con
ROUND_HALF_UP. Sin población, los totales son cero. Los promedios y la mediana
sin casos se muestran con un guion. La evolución separa volumen e importes.
El año completo usa cuatrimestres y un corte trimestral o cuatrimestral usa
meses, incluidos los tramos sin actividad. El ranking muestra hasta cinco
centros o grupos y permite desplegar la tabla completa. El ranking por correo
se consulta en un bloque secundario. Ambos se ordenan por cantidad de
solicitudes, importe solicitado o facturado neto.
Los correos compartidos no fusionan personas ni alteran titularidad.

Seguimiento muestra el estado actual de los trámites abiertos de la población
filtrada. Se cuentan solicitudes presentadas sin factura, cobros vigentes
pendientes de verificación y observaciones pendientes de subsanar. La
antigüedad muestra los días desde la presentación, registro del cobro o última
observación del caso más antiguo de cada acción. Se omite si falta el evento
necesario para medirla. Un trámite puede requerir más de una acción. Se enlaza
al listado cuando sus filtros existentes reproducen el mismo año y estado.

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

En Reporte, las pestañas preceden al título de cada circuito. Facturación ofrece
botones de año completo, tres cuatrimestres (enero–abril, mayo–agosto,
septiembre–diciembre) y cuatro trimestres (enero–marzo, abril–junio,
julio–septiembre, octubre–diciembre) para el año seleccionado. Se elige un único
período; cambiarlo conserva el año y el orden de grupos. Los parámetros de trimestre
y cuatrimestre simultáneos se rechazan. Las secciones Evolución, Demanda por
grupo y Seguimiento separan las escalas, las unidades y las acciones.
En ambos reportes, las selecciones aplican los filtros automáticamente mediante
GET. Limpiar filtros vuelve al año actual y los valores iniciales del circuito.
Sin JavaScript, se ofrece Actualizar reporte como alternativa.

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
