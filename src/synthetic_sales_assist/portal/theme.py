"""Shared local presentation tokens; qualitative user direction, no brand-guide claim."""

from typing import Final


DISPLAY_TITLE: Final = "ECS Sales Assist"
SYNTHETIC_COMPANION: Final = "Synthetic demo · Localhost only · Not connected to live systems"
THEME_TOKENS: Final = {
    "color-background": "#f3f4f5",
    "color-surface": "#ffffff",
    "color-header": "#181a1d",
    "color-text": "#202327",
    "color-muted": "#555b63",
    "color-border": "#ccd0d5",
    "color-input-border": "#747b84",
    "color-primary": "#bc1827",
    "color-primary-hover": "#971320",
    "color-primary-active": "#77101a",
    "color-secondary": "#454b52",
    "color-focus": "#246bce",
    "color-success": "#23663c",
    "color-success-surface": "#e6f3e9",
    "color-warning": "#6b4b00",
    "color-warning-surface": "#fff3cf",
    "color-warning-border": "#b77b00",
    "color-error": "#8a2030",
    "color-error-surface": "#fde7ec",
    "color-info": "#2c4c6b",
    "color-info-surface": "#eaf0f6",
    "font-family": 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    "space-1": ".25rem", "space-2": ".5rem", "space-3": ".75rem",
    "space-4": "1rem", "space-5": "1.25rem", "space-6": "1.5rem",
    "radius-control": ".35rem", "radius-surface": ".5rem",
    "border-width": "1px", "focus-width": "3px", "disabled-opacity": ".62",
    "shadow-surface": "0 2px 8px rgb(24 26 29 / 6%)",
}
THEME_CSS: Final = (
    "/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6; shared local presentation tokens */\n:root {\n"
    + "".join(f"  --ssa-{name}: {value};\n" for name, value in THEME_TOKENS.items())
    + "}\n"
)
