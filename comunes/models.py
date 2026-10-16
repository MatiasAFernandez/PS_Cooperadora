"""Cabecera estable: identidad y titular inmutables, sin estados de negocio."""

from django.db import IntegrityError, models

from .contracts import TramiteRef


class Circuito(models.TextChoices):
    GASTO = "GASTO", "Gastos"
    FACTURACION = "FACTURACION", "Facturación"


class TramiteBase(models.Model):
    circuito = models.CharField(max_length=20, choices=Circuito.choices, editable=False)
    numero_publico = models.PositiveIntegerField(editable=False)
    solicitante_actor_id = models.CharField(max_length=150, editable=False)
    # La unidad requirente existente no acredita un centro de costo.
    centro_costo_codigo = models.CharField(max_length=50, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["circuito", "numero_publico"], name="uq_tramite_circuito_numero_publico"
            ),
            models.CheckConstraint(
                condition=models.Q(circuito__in=Circuito.values), name="ck_tramite_circuito_valido"
            ),
            models.CheckConstraint(
                condition=models.Q(numero_publico__gt=0), name="ck_tramite_numero_positivo"
            ),
            models.CheckConstraint(
                condition=~models.Q(solicitante_actor_id=""), name="ck_tramite_titular_no_vacio"
            ),
        ]

    @property
    def referencia(self) -> TramiteRef:
        return TramiteRef(self.circuito, self.numero_publico)

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            campos = ("circuito", "numero_publico", "solicitante_actor_id")
            original = type(self).objects.filter(pk=self.pk).values(*campos).first()
            if original and any(getattr(self, c) != original[c] for c in campos):
                raise IntegrityError("La identidad y el titular del trámite son inmutables.")
        super().save(*args, **kwargs)
