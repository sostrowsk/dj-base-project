from django import template
from django.utils.http import urlencode

register = template.Library()

QUERY_PARAM_SINGLE_VALUE = ["page", "sort"]


@register.simple_tag(takes_context=True)
def query_param_add(context: dict, param_name: str | tuple[str, str], param_value: str) -> str:
    request_query = context["request"].GET.copy()
    param_value_normalized = str(param_value)
    param_name_normalized = f"{param_name[0]}:{param_name[1]}" if isinstance(param_name, tuple) else str(param_name)

    if param_name_normalized in QUERY_PARAM_SINGLE_VALUE:
        request_query[param_name_normalized] = param_value_normalized
    elif param_value_normalized not in request_query.getlist(param_name_normalized):
        request_query.pop("page", None)
        request_query.appendlist(param_name_normalized, param_value_normalized)

    query_string = urlencode(request_query, doseq=True)
    return f"?{query_string}"


@register.simple_tag(takes_context=True)
def query_param_remove(context: dict, param_name: str, param_value: str = None) -> str:
    request_query = context["request"].GET.copy()
    param_name_normalized = str(param_name)

    if param_name_normalized not in request_query:
        return ""

    if param_value is None:
        del request_query[param_name_normalized]
    else:
        current_values = request_query.getlist(param_name_normalized)
        filtered_values = [v for v in current_values if v != str(param_value)]

        if filtered_values:
            request_query.setlist(param_name_normalized, filtered_values)
        else:
            del request_query[param_name_normalized]

    query_string = urlencode(request_query, doseq=True)
    return f"?{query_string}" if query_string else ""
