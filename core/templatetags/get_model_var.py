from django import template

register = template.Library()

@register.filter()
def get_type_text(account, type):
    return account.get_type_text(type)
