from decimal import Decimal

from django import template
register = template.Library()

@register.filter
def decimal_normalise(num):
    d = Decimal(str(num));
    return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()

