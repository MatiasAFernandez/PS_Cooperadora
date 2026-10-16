"""Catálogos del formulario relevado; perfil provisional para la demo de #23."""

from django.db import models


class CondicionIVA(models.TextChoices):
    IVA_RESPONSABLE_INSCRIPTO = "IVA_RESPONSABLE_INSCRIPTO", "IVA Responsable Inscripto"
    IVA_SUJETO_EXENTO = "IVA_SUJETO_EXENTO", "IVA sujeto Exento"
    CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL", "Consumidor Final"
    RESPONSABLE_MONOTRIBUTO = "RESPONSABLE_MONOTRIBUTO", "Responsable Monotributo"
    PROVEEDOR_EXTERIOR = "PROVEEDOR_EXTERIOR", "Proveedor del Exterior"
    CLIENTE_EXTERIOR = "CLIENTE_EXTERIOR", "Cliente del Exterior"
    IVA_LIBERADO_19640 = "IVA_LIBERADO_19640", "IVA Liberado - Ley N° 19.640"
    IVA_RI_AGENTE_PERCEPCION = "IVA_RI_AGENTE_PERCEPCION", "IVA Resp Insc- Agente de Percepción"
    MONOTRIBUTO_SOCIAL = "MONOTRIBUTO_SOCIAL", "Monotributo Social"
    IVA_NO_ALCANZADO = "IVA_NO_ALCANZADO", "IVA No Alcanzado"


class ProductoServicio(models.TextChoices):
    ABONO_MENSUAL = "ABONO_MENSUAL", "Abono Mensual"
    ALQUILER = "ALQUILER", "Alquiler"
    ANALISIS = "ANALISIS", "Análisis"
    ANALISIS_DOSIMETRIA = "ANALISIS_DOSIMETRIA", "Análisis de Dosimetria"
    BIENES_DE_CAPITAL = "BIENES_DE_CAPITAL", "Bienes de Capital"
    CAPACITACION_CONVENIO = "CAPACITACION_CONVENIO", "Capacitación según Convenio"
    CONSULTORIA_Y_SERVICIOS = "CONSULTORIA_Y_SERVICIOS", "Consultoria y Servicios"
    CONVENIO_RADIO = "CONVENIO_RADIO", "Convenio Radio"
    CORRESPONDENCIA_ENVIO = "CORRESPONDENCIA_ENVIO", "Correspondencia/Envio"
    COOPERADORA = "COOPERADORA", "Cooperadora"
    CUOTA_SOCIETARIA_COOP = "CUOTA_SOCIETARIA_COOP", "Cuota Societaria Asoc. Coop"
    CURSOS_CISCO = "CURSOS_CISCO", "Cursos Cisco"
    CURSOS_CAPACITACION_ELEARNING = (
        "CURSOS_CAPACITACION_ELEARNING",
        "Cursos de capacitación E-Learning",
    )
    CURSOS_CAPACITACION_VIRTUAL = (
        "CURSOS_CAPACITACION_VIRTUAL",
        "Cursos de Capacitación Modalidad Virtual",
    )
    CURSOS_CAPACITACION_PRESENCIAL = (
        "CURSOS_CAPACITACION_PRESENCIAL",
        "Cursos de Capacitación Presencial",
    )
    ESPACIO_DE_RADIO = "ESPACIO_DE_RADIO", "Espacio de Radio"
    EVENTOS = "EVENTOS", "Eventos"
    EXAMEN_OXFORD = "EXAMEN_OXFORD", "Examen Oxford Test of English"
    GISTAQ_ANALISIS_AGUA = "GISTAQ_ANALISIS_AGUA", "GISTAQ- Análisis de Agua"
    GISTAQ_ANALISIS_CARBON = "GISTAQ_ANALISIS_CARBON", "GISTAQ- Análisis de Carbon"
    GISTAQ_SERVICIOS = "GISTAQ_SERVICIOS", "GISTAQ Servicios"
    HONORARIOS = "HONORARIOS", "Honorarios"
    IMPRESIONES = "IMPRESIONES", "Impresiones"
    INSUMOS_MANTENIMIENTO = "INSUMOS_MANTENIMIENTO", "Insumos de Mantenimiento"
    INSUMOS_LABORATORIO = "INSUMOS_LABORATORIO", "Insumos de Laboratorio"
    INSUMOS_INFORMATICOS = "INSUMOS_INFORMATICOS", "Insumos Informaticos"
    PROYECTO_UVT = "PROYECTO_UVT", "Proyecto UVT"
    QUIMOBI_ANALISIS_BIODIESEL = "QUIMOBI_ANALISIS_BIODIESEL", "QUIMOBI- Análisis de Biodiesel"
    QUIMOBI_SERVICIOS = "QUIMOBI_SERVICIOS", "QUIMOBI- Servicios"
    QUITEX_ANALISIS_CERVEZA = "QUITEX_ANALISIS_CERVEZA", "QUITEX- Análisis de Cerveza"
    QUITEX_ANALISIS_PRODUCTOS = "QUITEX_ANALISIS_PRODUCTOS", "QUITEX- Análisis de Productos"
    REINTEGRO = "REINTEGRO", "Reintegro"
    REINTEGROS_GASTOS = "REINTEGROS_GASTOS", "Reintegros gastos"
    SERVICIOS_AUDITORIAS = "SERVICIOS_AUDITORIAS", "Servicios de Auditorias"
    TRABAJOS_MANTENIMIENTO = "TRABAJOS_MANTENIMIENTO", "Trabajos de mantenimiento"
    UVT = "UVT", "UVT"
    VIATICOS = "VIATICOS", "Viaticos"
    OTROS = "OTROS", "Otros"


class CentroCosto(models.TextChoices):
    ALQUILER = "ALQUILER", "Alquiler"
    AULA_MAGNA = "AULA_MAGNA", "Aula Magna"
    OPCION_35 = "OPCION_35", "Opción 35"
    AUSPICIO = "AUSPICIO", "Auspicio"
    BIBLIOTECA = "BIBLIOTECA", "Biblioteca"
    BIOTEC = "BIOTEC", "Biotec"
    CAPACITACION = "CAPACITACION", "Capacitación"
    CAPACITACION_ELEARNING = "CAPACITACION_ELEARNING", "Capacitación Elearning"
    CET = "CET", "CET"
    CINAPTIC = "CINAPTIC", "CINAPTIC"
    CISCO = "CISCO", "CISCO"
    COOPERADORA = "COOPERADORA", "Cooperadora"
    EVENTO = "EVENTO", "Evento"
    GESTION_TECNOLOGICA = "GESTION_TECNOLOGICA", "Gestion Tecnologica"
    GISTAQ = "GISTAQ", "GISTAQ"
    GITEA = "GITEA", "GITEA"
    INTECNOR = "INTECNOR", "INTECNOR"
    LAB_FISICA = "LAB_FISICA", "Lab Fisica"
    LAB_QUIMICA = "LAB_QUIMICA", "Lab Química"
    MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"
    POSGRADO = "POSGRADO", "Posgrado"
    QUIMOBI = "QUIMOBI", "QUIMOBI"
    QUITEX = "QUITEX", "QUITEX"
    RADIO = "RADIO", "Radio"
    RRHH = "RRHH", "RRHH"
    RRII = "RRII", "RRII"
    SACAD = "SACAD", "SACAD"
    SADMIN = "SADMIN", "SADMIN"
    SAU = "SAU", "SAU"
    SAU_DEPORTES = "SAU_DEPORTES", "SAU-Deportes"
    SCYT = "SCYT", "SCYT"
    SEU = "SEU", "SEU"
    STERCEROS = "STERCEROS", "STERCEROS"
    UTD = "UTD", "UTD"
    UVT = "UVT", "UVT"


class ModalidadCobro(models.TextChoices):
    MERCADO_PAGO = "MERCADO_PAGO", "Mercado Pago"
    BNA_COMUN = "BNA_COMUN", "Banco Nación Cuenta Comun"
    BNA_UVT = "BNA_UVT", "Banco Nación Cuenta UVT"
    NBCH = "NBCH", "Nuevo Banco del Chaco"
    CUENTA_CORRIENTE = (
        "CUENTA_CORRIENTE",
        "Cuenta corriente (aún no se cobró la factura que se va a emitir)",
    )


MEDIOS_PAGO_EFECTIVOS = frozenset({"MERCADO_PAGO", "BNA_COMUN", "BNA_UVT", "NBCH"})
