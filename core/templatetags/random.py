import random
from django import template

register = template.Library()


@register.simple_tag
def random_list():
    listt = ["warning", "info", "success", "danger", "primary"]
    return random.choice(listt)
