"""
Lucide Icons template tag for Django.

Usage:
    {% load lucide_tags %}
    {% lucide "x" %}
    {% lucide "check" class="w-5 h-5 text-green-500" %}
"""

import re
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Cache for loaded SVGs, keyed by absolute icon path
_icon_cache: dict[str, str] = {}


def _icons_dir() -> Path:
    """Resolve the lucide-static icons directory via the LUCIDE_ICONS_DIR setting."""
    default = Path(settings.BASE_DIR) / "node_modules" / "lucide-static" / "icons"
    return Path(getattr(settings, "LUCIDE_ICONS_DIR", default))


# Font Awesome to Lucide icon mapping
FA_TO_LUCIDE: dict[str, str] = {
    # Close / X marks
    "xmark": "x",
    "times": "x",
    "circle-xmark": "x-circle",
    "file-circle-xmark": "file-x",
    "building-circle-xmark": "building",
    "filter-circle-xmark": "filter-x",
    # Check marks
    "check": "check",
    "circle-check": "circle-check",
    "building-circle-check": "building",
    # Navigation
    "chevron-right": "chevron-right",
    "chevron-down": "chevron-down",
    "chevron-left": "chevron-left",
    "angle-right": "chevron-right",
    "angle-left": "chevron-left",
    "angle-double-right": "chevrons-right",
    "angle-double-left": "chevrons-left",
    "arrow-left": "arrow-left",
    "arrow-right": "arrow-right",
    "arrow-up-right-from-square": "external-link",
    # User / People
    "user": "user",
    "users": "users",
    "user-tie": "user",
    "user-plus": "user-plus",
    "user-gear": "user-cog",
    "user-check": "user-check",
    "user-unlock": "unlock",
    "users-slash": "users",
    # Building / Organization
    "building": "building-2",
    "buildings": "building-2",
    # Communication
    "envelope": "mail",
    "envelope-open": "mail-open",
    "envelopes": "mails",
    "paper-plane": "send",
    "reply": "reply",
    "comments": "message-circle",
    "message": "message-square",
    "message-lines": "message-square-text",
    "bell": "bell",
    # Files / Documents
    "file": "file",
    "files": "files",
    "file-lines": "file-text",
    "file-alt": "file-text",
    "file-pdf": "file-text",
    "file-word": "file-text",
    "file-excel": "file-spreadsheet",
    "file-invoice": "file-text",
    "file-contract": "file-signature",
    "file-signature": "file-signature",
    "file-arrow-down": "file-down",
    "file-export": "file-output",
    "file-circle-question": "file-question",
    # Folders
    "folder": "folder",
    "folder-open": "folder-open",
    "folder-plus": "folder-plus",
    # Actions
    "download": "download",
    "cloud-arrow-up": "cloud-upload",
    "plus": "plus",
    "plus-circle": "circle-plus",
    "trash-can": "trash-2",
    "trash": "trash-2",
    "pen-to-square": "pencil",
    "pen": "pen",
    "save": "save",
    "floppy-disk": "save",
    "print": "printer",
    # Time / Date
    "clock": "clock",
    "clock-rotate-left": "history",
    "calendar": "calendar",
    "calendar-pen": "calendar",
    "calendar-check": "calendar-check",
    "watch": "watch",
    "hourglass-start": "hourglass",
    "hourglass-half": "hourglass",
    "hourglass-end": "hourglass",
    # Search
    "search": "search",
    "magnifying-glass": "search",
    # Status / Info
    "circle-info": "info",
    "info-circle": "info",
    "info": "info",
    "circle-question": "circle-help",
    "question": "help-circle",
    "triangle-exclamation": "alert-triangle",
    "exclamation-triangle": "alert-triangle",
    "exclamation": "alert-triangle",
    "circle-exclamation": "alert-circle",
    "comment-exclamation": "message-circle",
    "lightbulb": "lightbulb",
    "ban": "ban",
    # Eye / View
    "eye": "eye",
    "eye-slash": "eye-off",
    # Phone
    "phone": "phone",
    # Business / Professional
    "briefcase": "briefcase",
    "clipboard": "clipboard",
    "clipboard-list": "clipboard-list",
    "calculator": "calculator",
    "chart-line": "chart-line",
    "chart-pie": "chart-pie",
    "handshake": "handshake",
    # Lists
    "list": "list",
    "tasks": "list-checks",
    # Layout
    "table-columns": "columns-2",
    "inbox": "inbox",
    "layer-group": "layers",
    # Misc
    "globe": "globe",
    "hashtag": "hash",
    "book": "book",
    "id-card": "id-card",
    "key": "key",
    "lock": "lock",
    "shield": "shield",
    "star": "star",
    "sticky-note": "sticky-note",
    "note-sticky": "sticky-note",
    "bolt": "zap",
    "link": "link",
    "link-slash": "unlink",
    "font": "type",
    "circle": "circle",
    # Toggle
    "toggle-on": "toggle-right",
    "toggle-off": "toggle-left",
    # Sort
    "sort-numeric-down": "arrow-down-0-1",
    "sort-numeric-up": "arrow-up-0-1",
    "sort-alpha-down": "arrow-down-a-z",
    "sort-alpha-up": "arrow-up-a-z",
    "filter-slash": "filter-x",
    # AI / Tech
    "microchip-ai": "cpu",
    "sparkles": "sparkles",
    "robot": "bot",
    "wand-magic-sparkles": "wand-2",
    # Sign in/out
    "sign-out": "log-out",
    # Additional icons
    "spinner": "loader-2",
    "external-link-alt": "external-link",
    "redo": "refresh-cw",
    "file-zipper": "archive",
    "sort": "arrow-up-down",
    "file-image": "image",
    # Migration batch — FA names used in templates without prior mapping
    "address-card": "contact",
    "arrows-rotate": "refresh-cw",
    "building-columns": "landmark",
    "calendar-days": "calendar-days",
    "check-circle": "check-circle",
    "clipboard-question": "clipboard-list",
    "copy": "copy",
    "display-chart-up-circle-dollar": "bar-chart-2",
    "edit": "pencil",
    "euro-sign": "euro",
    "exclamation-circle": "alert-circle",
    "file-zip": "file-archive",
    "gears": "settings",
    "industry-windows": "factory",
    "magnifying-glass-plus": "zoom-in",
    "mailbox": "mailbox",
    "mailbox-flag-up": "mailbox",
    "play-circle": "play-circle",
    "quote-left": "quote",
    "rectangle-history": "history",
    "remove": "circle-minus",
    "seedling": "sprout",
    "sitemap": "network",
    "sort-down": "arrow-down",
    "sort-up": "arrow-up",
    "square-check": "square-check",
    "store": "store",
    "th-large": "grid-2x2-check",
    "truck": "truck",
    "unlink": "unlink",
}


def _load_icon(name: str) -> str | None:
    """Load SVG content from lucide-static package."""
    icon_path = _icons_dir() / f"{name}.svg"
    cache_key = str(icon_path)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    if not icon_path.exists():
        return None

    svg_content = icon_path.read_text()
    _icon_cache[cache_key] = svg_content
    return svg_content


def _merge_classes(svg: str, extra_classes: str) -> str:
    """Merge extra classes into SVG class attribute."""
    if not extra_classes:
        return svg

    # Match class="..." in the SVG tag
    class_pattern = r'class="([^"]*)"'
    match = re.search(class_pattern, svg)

    if match:
        existing = match.group(1)
        new_classes = f"{existing} {extra_classes}"
        return re.sub(class_pattern, f'class="{new_classes}"', svg, count=1)
    else:
        # Add class attribute after <svg
        return svg.replace("<svg", f'<svg class="{extra_classes}"', 1)


@register.simple_tag
def lucide(name: str, **kwargs) -> str:
    """
    Render a Lucide icon as inline SVG.

    Args:
        name: Icon name (e.g., "x", "check", "chevron-right")
        class_: CSS classes to add to the SVG (use class_ because class is reserved)
        **kwargs: Additional attributes to add to the SVG

    Returns:
        Safe HTML string with the SVG icon

    Example:
        {% lucide "x" %}
        {% lucide "check" class="w-5 h-5 text-green-500" %}
        {% lucide "download" class="w-4 h-4" id="download-icon" %}
    """
    svg = _load_icon(name)

    if svg is None:
        # Return empty span with warning class for debugging
        return format_html('<span class="lucide-missing" data-icon="{}"></span>', name)

    # Handle class separately (class_ because 'class' is Python reserved word)
    extra_classes = kwargs.pop("class", "") or kwargs.pop("class_", "")
    svg = _merge_classes(svg, extra_classes)

    # Add any additional attributes
    if kwargs:
        attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kwargs.items())
        svg = svg.replace("<svg", f"<svg {attrs}", 1)

    return mark_safe(svg)


def _get_lucide_name(fa_name: str) -> str:
    """Convert Font Awesome icon name to Lucide icon name."""
    return FA_TO_LUCIDE.get(fa_name, fa_name)


@register.simple_tag
def icon(name: str, **kwargs) -> str:
    """
    Render an icon - auto-maps Font Awesome names to Lucide equivalents.

    This is a convenience wrapper that accepts FA icon names and
    automatically converts them to Lucide icons.

    Args:
        name: Icon name (FA or Lucide, e.g., "xmark" or "x")
        **kwargs: Same as lucide tag

    Example:
        {% icon "xmark" %}  {# FA name, converted to Lucide "x" #}
        {% icon "check" class="w-5 h-5 text-green-500" %}
    """
    lucide_name = _get_lucide_name(name)
    return lucide(lucide_name, **kwargs)
