# Self Manager development

## Shared visual style

All new pages and visual changes must follow the homepage's light Self Manager style.

- Use `apps/shared/theme.css` as the source of truth for colors, typography, page width, spacing, surfaces, and controls. Add reusable theme tokens or primitives there rather than duplicating them in individual pages.
- Vue entries import `../../shared/theme.css` before page-specific CSS. Static pages load `/shared/theme.css` before their own stylesheet.
- Use the `sm-header`, `sm-brand`, `sm-mark`, `sm-container`, `sm-intro`, `sm-title`, `sm-panel`, `sm-button`, and `sm-control` classes for common page elements. Page-specific CSS should describe domain layouts and interactions.
- Keep the cream background, dark green text, muted green accents, light cards, subtle borders, and restrained shadows. Do not introduce an independent dark theme or hardcode a replacement palette into components or SVG charts.
- Start from `apps/shared/page-template.html` and follow `docs/ui-style.md` when adding a page. Include a route back to the homepage and check narrow/mobile layouts and keyboard focus.
- Legacy strength/investment pages can adopt the shared theme when their UI is next changed; do not redesign unrelated tools as part of a small change.

## Frontend artifacts

Keep dependency installations, generated lockfiles, and build output in the module's ignored `.generated/` directory. Rebuild each affected Vue application after changing shared CSS. Run the relevant existing browser regression tests for functional UI changes.
