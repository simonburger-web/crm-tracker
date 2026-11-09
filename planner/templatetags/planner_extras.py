from django import template

register = template.Library()


@register.filter
def hm(minutes):
    """90 -> '1h 30m', 45 -> '45m'."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""
    sign = "-" if minutes < 0 else ""
    h, m = divmod(abs(minutes), 60)
    if h and m:
        return f"{sign}{h}h {m}m"
    return f"{sign}{h}h" if h else f"{sign}{m}m"
