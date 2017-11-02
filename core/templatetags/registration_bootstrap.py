# coding=utf-8
from django import template
from django.http import QueryDict

register = template.Library()

@register.filter()
def add_class(field, css):
   return field.as_widget(attrs={"class":css})



@register.filter
def add_attrs(field, attr):
    qs = QueryDict(attr)
    attrs = {}
    for key, value in qs.items():
       attrs[key] = value

    return field.as_widget(attrs=attrs)