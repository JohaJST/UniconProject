import random
from django import template

register = template.Library()


@register.simple_tag
def random_list():
    listt = ["warning", "info", "success", "danger", "primary"]
    return random.choice(listt)

@register.filter
def initials(full_name):
    """Инициалы для аватарки преподавателя без фото: 'Каримов Aziz' -> 'КA'."""
    parts = (full_name or '').split()
    return ''.join(p[0] for p in parts[:2]).upper()