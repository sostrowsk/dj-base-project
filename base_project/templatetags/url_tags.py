from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def fully_qualified_url(context, url):
    return context["request"].build_absolute_uri(url)
