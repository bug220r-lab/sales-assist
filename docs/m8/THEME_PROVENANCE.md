# ECS-inspired presentation

The user amendment in `tasks/presentation_amendment.txt` authorizes the exact
presentation title ECS Sales Assist and the visible companion label
Synthetic demo · Localhost only · Not connected to live systems.
This is a synthetic local demo, without a production or corporate approval claim.

No approved local logo or brand guide was supplied. Logo matching and exact corporate
color/typeface matching remain PENDING. The wordmark is plain text; no trademark logo
was invented or downloaded. All colors below are implementation choices derived from
the user's qualitative red/charcoal/white/light-gray direction, not verified ECS standards.
There are no third-party fonts, images, analytics, stylesheets, or asset requests.

The authoritative named tokens are in `src/synthetic_sales_assist/portal/theme.py`.
Portal and dashboard CSS include that token block; `chrome_extension/shared/theme.css`
is its byte-identical packaged copy. System sans-serif fonts remain installed prerequisites.
The shared set also defines spacing, borders, radii, focus, disabled state, and shadows.

| Color token | Chosen value |
|---|---|
| `color-background` | `#f3f4f5` |
| `color-surface` | `#ffffff` |
| `color-header` | `#181a1d` |
| `color-text` | `#202327` |
| `color-muted` | `#555b63` |
| `color-border` | `#ccd0d5` |
| `color-input-border` | `#747b84` |
| `color-primary` | `#bc1827` |
| `color-primary-hover` | `#971320` |
| `color-primary-active` | `#77101a` |
| `color-secondary` | `#454b52` |
| `color-focus` | `#246bce` |
| `color-success` | `#23663c` |
| `color-success-surface` | `#e6f3e9` |
| `color-warning` | `#6b4b00` |
| `color-warning-surface` | `#fff3cf` |
| `color-warning-border` | `#b77b00` |
| `color-error` | `#8a2030` |
| `color-error-surface` | `#fde7ec` |
| `color-info` | `#2c4c6b` |
| `color-info-surface` | `#eaf0f6` |

The application and extension versions are both 0.1.2. Internal names, API/DOM schemas,
command namespaces, rules, Money, database schema 4, and loopback host permissions remain
unchanged. CSP remains local. No scanner exemption was needed for the authorized title.
Safety rejection tests continue to cover real identities, secrets, and non-loopback URLs.

The automated theme tests check shared assets, local references, visible labels and
text/button/focus contrast. Browser evidence distinguishes the in-app web surfaces and
static panel preview from native Chrome acceptance, which remains pending until performed.
Actual screenshots and capability limits are supplied in external release evidence.
