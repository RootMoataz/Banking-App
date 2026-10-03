# Paper Maker design brief

Source of truth is the code: `src/styles.css` (app, and all tokens in `:root`) and `src/landing.css` (public page, scoped under `.landing`). If this page and the CSS disagree, the CSS wins; fix this page.

## Identity: a banknote, made visible

The product is a learning bank, so the look is a printed banknote: a deep green note, a fine gold double border, and a round mascot medallion. Paper-pale green grounds, white cards, and calm ink text keep the working screens quiet. The mascot logo sits in a white tile or medallion; the landing page shows a sample note with a gold border, an inner hairline and a rosette pattern.

## Colour (use tokens only)

- Greens: `--forest-deep`, `--forest` (headings, top bar), `--brand-dark`, `--brand` (buttons, links), `--brand-mid`, `--leaf`, `--sage`.
- Mint tints: `--brand-tint` (hover, current nav, soft fills), `--green-tint` (success).
- Ground and surfaces: `--page` (pale green paper), `--card` (white), `--line`, `--line-strong`, `--field` (input borders).
- Text: `--ink`, `--muted`, `--on-dark`.
- Gold: `--gold` and `--gold-light`.
- Red (`--red`, `--red-tint`, `--red-ink`): errors and destructive actions only.
- Tape (`--tape`, `--tape-line`): the cream receipt strip for transaction history.

## Type

- Display: Newsreader 500/600, on the landing page headings and brand only.
- Interface: IBM Plex Sans 400/500/600 (`--sans`), 16px base, 1.5 line height. App headings are Plex Sans 600 in `--forest` (h1 28px, 24px on phones; h2 20px).
- Figures and IDs: IBM Plex Mono (`--mono`), with tabular numbers for money.

## Space and shape

- Radius: `--radius` 12px (cards, panels, dialogs), `--radius-sm` 8px (buttons, inputs).
- Rhythm: gaps and padding step through 4, 8, 12, 16, 20, 24, 28; panels use 24/28px padding (20/18 on phones). Page content is capped at 1120px.
- Top bar is 64px (`--topbar`); side nav is 248px.

## Gold trim

- Gold is a hairline: a 1px bar under headers, a 2px+1px inset double border on filled buttons, the medallion ring, dashed dividers, and short rules under landing headings. The auth card and role table carry a 4px gold top rule.
- No gold text on light grounds. Gold-light text appears only on deep green (the sample note, footer links).
- Never gold on errors, danger buttons or red states. Secondary and danger buttons carry no gold.

## Motion

Short, calm and purposeful: 0.15s colour changes, a gentle settle on the sample note, a pulse on loading skeletons. Under `prefers-reduced-motion: reduce` all animations and transitions are turned off, and smooth scrolling is off on the landing page. New motion must respect this.

## Accessibility

- Text contrast 4.5:1 or better; UI parts (input borders, focus rings, icons) 3:1 or better. Disabled and muted text still meet 4.5:1.
- Tap targets at least 44px high; phone layouts (900px and below) keep every action button at 44px.
- Focus is always visible: 3px ring in `--brand` (white on dark grounds, red on danger buttons).
- Everything works from the keyboard: skip link on the landing page, dialogs trap and restore focus, focus returns to the control that opened a panel.
- Errors use `role="alert"` and say "Error." in text, so colour is never the only signal. Status messages use a polite live region. Each screen sets its own page title.

## Copy

Truthful and plain. This is an educational project, not a real bank: no real money, cards or payments, not regulated or insured, and say so where it matters (landing hero, landing disclaimer, footer). No promises of rates, safety or approval. Short sentences, the user's words, no jargon. Amounts show two decimals with no currency symbol.

## Responsive breakpoints in use

- App (`styles.css`): 900px (side nav becomes a menu drawer, tables stack into rows, 44px actions) and 720px (single-column summary tiles, smaller headings and padding, tape rows, full-width dialog buttons).
- Landing (`landing.css`): 1180px (menu button replaces the header links), 960px (hero and split sections go single column), 860px (ledger single column), 720px (steps, roles and cards stack, full-width buttons), 480px (decorative stamp hidden).
- Checked viewports: 1280x800 and 390x844.

## Anti-patterns (do not ship)

1. No purple or blue-violet gradients, and no gradient-heavy hero backgrounds. Greens, paper and gold only.
2. No Inter or system-default look. Pair Newsreader with IBM Plex; do not add other families.
3. No generic card grid of identical icon, title and blurb tiles. Use banknote, ledger, tape and table forms.
4. No decorative gold text, and no gold fills on light grounds. Gold is trim.
5. No new colours outside the tokens. Add or adjust a token in `:root` first, with a stated contrast reason.
