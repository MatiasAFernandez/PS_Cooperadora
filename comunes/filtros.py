"""Períodos de presentación compartidos por los dos listados."""

from datetime import date, datetime, time

from django import forms
from django.utils import timezone


class FiltroFechaForm(forms.Form):
    periodo = forms.ChoiceField(
        label="Fecha de presentación",
        required=False,
        choices=[("", "Todas las fechas"), ("dia", "Día exacto"), ("mes", "Mes"), ("anio", "Año")],
    )
    dia = forms.DateField(
        label="Día", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    mes = forms.IntegerField(label="Mes (1–12)", min_value=1, max_value=12, required=False)
    anio = forms.IntegerField(label="Año", min_value=1900, max_value=9998, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(["estado", "q", "periodo", "dia", "mes", "anio"])
        if self.is_bound:
            self.data = self.data.copy()
            activos = {"dia": {"dia"}, "mes": {"mes", "anio"}, "anio": {"anio"}}.get(
                self.data.get("periodo"), set()
            )
            for campo in {"dia", "mes", "anio"} - activos:
                self.data.pop(campo, None)

    def clean(self):
        datos = super().clean()
        campos = {"dia": ("dia",), "mes": ("mes", "anio"), "anio": ("anio",)}
        for campo in campos.get(datos.get("periodo"), ()):
            if not datos.get(campo) and campo not in self.errors:
                self.add_error(campo, "Completá este dato para el período seleccionado.")
        if datos.get("dia") == date.max:
            self.add_error("dia", "Seleccioná una fecha anterior al 31/12/9999.")
        return datos

    def filtrar_fecha(self, consulta, campo):
        datos = self.cleaned_data
        periodo = datos.get("periodo")
        if not periodo:
            return consulta
        if periodo == "dia":
            inicio = datos["dia"]
            from datetime import timedelta

            fin = inicio + timedelta(days=1)
        elif periodo == "mes":
            anio, mes = datos["anio"], datos["mes"]
            inicio = date(anio, mes, 1)
            fin = date(anio + (mes == 12), 1 if mes == 12 else mes + 1, 1)
        else:
            inicio, fin = date(datos["anio"], 1, 1), date(datos["anio"] + 1, 1, 1)
        zona = timezone.get_current_timezone()
        return consulta.filter(
            **{
                f"{campo}__gte": timezone.make_aware(datetime.combine(inicio, time.min), zona),
                f"{campo}__lt": timezone.make_aware(datetime.combine(fin, time.min), zona),
            }
        )
