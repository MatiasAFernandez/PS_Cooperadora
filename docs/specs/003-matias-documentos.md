# SPEC-003 — Documentos protegidos de los trámites

- Estado: borrador; pendiente de validación con Cooperadora y Franco.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: acordar tipos y momentos documentales del circuito de gastos y
  revisar la integración de acceso.
- Validadores: Cooperadora para documentos y política de archivos; Franco y Matías
  para el contrato común.
- Plan: RF-004, RNF-001, RNF-004, M-E04 e I03.

## Problema y valor

Los respaldos hoy están dispersos y pueden ser sensibles. Ambos circuitos deben
incorporar, clasificar, consultar y revisar documentos ligados al trámite, con
acceso controlado y una referencia clara a su procedencia.

## Alcance

### Incluye

- Carga de archivos permitidos, metadatos de tipo y relación con el trámite.
- Consulta y recuperación de archivos a través de controles de autorización.
- Registro de la revisión documental y consulta de su resultado por usuarios
  autorizados, según reglas por acordar.
- Almacenamiento configurable para archivos y metadatos en PostgreSQL.

### No incluye

- Publicar archivos mediante rutas estáticas abiertas.
- Aceptar automáticamente un documento por haberlo cargado.
- Definir aquí la deuda posterior a un pago ni el bloqueo de nuevas solicitudes.

## Requisitos verificables

- `DOC-R01`: cada documento se asocia a un trámite y conserva tipo y procedencia.
- `DOC-R02`: un archivo con tipo o tamaño fuera de la política acordada se rechaza
  sin crear un documento válido.
- `DOC-R03`: una persona sin permiso no puede recuperar el archivo ni consultar
  sus metadatos por un identificador directo.
- `DOC-R04`: una revisión deja trazabilidad del actor, resultado y fecha, conforme
  al contrato de historial compartido.

## Reglas de negocio

- La política de tipos, tamaño máximo, versiones y revisión queda pendiente de
  validación; los límites técnicos concretos se fijarán antes de implementar la carga.
- La autorización se comprueba en cada descarga y consulta, no sólo al mostrar
  enlaces en la interfaz.
- Un pendiente documental sólo se considera satisfecho cuando se cumpla la regla
  de revisión validada para el circuito correspondiente.

## Criterios de aceptación

1. Dado un archivo permitido y un trámite accesible, cuando un usuario autorizado
   lo incorpora, entonces se conserva el archivo con tipo y vínculo al trámite.
2. Dado un archivo inválido, cuando se intenta cargarlo, entonces se rechaza sin
   dejar un documento utilizable ni cambios parciales.
3. Dado un usuario ajeno, cuando solicita directamente un archivo de otro trámite,
   entonces no recibe el contenido.

## Datos, permisos y sensibilidad

- Datos requeridos: vínculo al trámite, tipo, procedencia, referencia de archivo,
  autor y fecha; resultado de revisión cuando corresponda.
- Roles autorizados: quien aporte o revise según el circuito y permisos validados.
- Datos sintéticos o anonimizados para pruebas: archivos de ejemplo sin información
  personal ni financiera real.

## Módulos e interfaces

- Módulo propietario: componente documental común, a cargo de Matías.
- Entradas y salidas: trámite autorizado + archivo/metadatos → documento asociado;
  solicitud de recuperación → archivo o denegación.
- Dependencias: SPEC-002 para permisos y SPEC-009 para identificadores compartidos.
- Integración requerida: facturas/notas en SPEC-005, cobros en SPEC-006 y gastos de
  Franco en un incremento posterior a SPEC-001.

## Estrategia de prueba y evidencia

- Pruebas unitarias: validación de política de archivo y metadatos.
- Pruebas de integración: carga, revisión y descarga autorizada/denegada con
  almacenamiento de prueba y PostgreSQL.
- Demostración o evidencia: archivo ficticio asociado al trámite y recuperación
  permitida sólo desde una identidad autorizada.

## Preguntas abiertas

- ¿Qué tipos documentales y tamaños se permiten en cada circuito?
- ¿Quién puede aportar, reemplazar, revisar o rechazar documentos? ¿Se guardan
  versiones?
- ¿Qué criterios hacen que un documento satisfaga un pendiente?
- ¿Dónde se alojarán los archivos en el entorno institucional de prueba?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Documentos comunes con almacenamiento configurable y acceso controlado. | La política concreta y los tipos se validan antes de implementar. |
