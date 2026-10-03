# Paper Maker design brief

Source of truth is the code: `src/styles.css` (app, and all tokens in `:root`) and `src/landing.css` (public page, scoped under `.landing`). If this page and the CSS disagree, the CSS wins; fix this page.

## Identity: an engraved note, made visible

The product is a learning bank, so the look is a printed banknote: deep green, fine gold double borders, engraved lathe work (overlapping circles) and a round mascot medallion. Three grounds carry it:

- **Deep note** (forest gradient + gold lathe): landing hero, controls section, top bar, sign-in panel, and the lead summary tile in the app (no mascot there). Gold-light text lives here.
- **Paper** (`--page` with faint green lathe): working screens stay quiet. White cards and tables with a gold top rule.
- **Account note** (`--note-paper` + green lathe + gold double border + wave frame): each account card, the empty state.

The landing hero fans two plain notes behind the interactive sample note. Sections are joined by a perforated edge (stamp scallops), not a flat line.

## Colour (use tokens only)

- Greens: `--forest-deep`, `--forest` (headings, top bar), `--brand-dark`, `--brand` (buttons, links), `--brand-mid`, `--leaf`, `--sage`.
- Mint tints: `--brand-tint` (hover, table head, soft fills), `--green-tint` (success).
- Ground and surfaces: `--page`, `--card`, `--note-paper` (account notes, ledger), `--note-sage` and `--note-tan` (fan notes), `--line`, `--line-strong`, `--field`.
- Text: `--ink`, `--muted`, `--on-dark`, `--cream` (headings on deep green).
- Gold: `--gold` and `--gold-light`.
- Red (`--red`, `--red-tint`, `--red-ink`): errors and destructive actions only.
- Tape (`--tape`, `--tape-line`): the cream receipt strip for transaction history.
- Depth: `--shadow-1/2/3` (green-tinted, never grey) and `--highlight` (1px inset top light).
- Texture: `--lathe-green` (on paper) and `--lathe-gold` (on deep green), 40px SVG tiles. Keep alpha low; they must never fight text.

## Type

- Display: Newsreader 500/600 (`--display`) for every h1/h2/h3, the brand name, account balances, summary figures and empty-state titles. Use lining tabular numerals for money.
- Interface: IBM Plex Sans 400/500/600 (`--sans`), 16px base, 1.5 line height. App h1 is 34px (28px on phones), h2 24px.
- Figures and IDs: IBM Plex Mono (`--mono`) for serials, account IDs and the tape.
- No other families.

## Space and shape

- Radius: `--radius` 12px (cards, panels, dialogs), `--radius-sm` 8px (buttons, inputs).
- Rhythm: gaps and padding step through 4, 8, 12, 16, 20, 24, 28; panels use 26/28px padding (20/18 on phones). Page content is capped at 1120px.
- Page headings end in a double rule (`3px double`), the ledger motif. Top bar is 64px (`--topbar`); side nav is 248px with a line icon per item (inline SVG in `ui.jsx`, `Icon`).

## Gold trim

- Gold is a hairline: 1px under headers, a 2px+1px inset double border on filled buttons, the medallion ring, dashed or double dividers, and 3-4px top rules on panels, tables, the auth card and the role table.
- No gold text on light grounds. Gold-light text appears only on deep green (lead tile figure, sample note, footer links).
- Gold fills only on deep green (the hero's primary buttons, with an inverse forest trim).
- Never gold on errors, danger buttons or red states. Secondary and danger buttons carry no gold. The delete dialog has a red top rule instead.

## Depth and motion

- Buttons are tactile: inset trim plus a tinted drop shadow, 1px lift on hover, 1px press on active. Inputs have an inset shadow and a soft focus halo. Account notes lift on hover.
- Selected toggles (History) use `aria-pressed` and a solid forest fill. A disabled Delete is dashed and grey, with a visible "Delete needs a zero balance." line on the card.
- Orchestrated moments only: the sample note settling on the landing hero, and the lead summary figure counting up once (`CountUp` in `ui.jsx`).
- Everything else is 0.15s colour/shadow changes. Under `prefers-reduced-motion: reduce` all animations and transitions are off, the count-up is skipped, and smooth scrolling is off on the landing page. New motion must respect this.

## Accessibility

- Text contrast 4.5:1 or better; UI parts (input borders, focus rings, icons) 3:1 or better. Disabled and muted text still meet 4.5:1. Measured pairings: gold-light on `--brand-dark` 4.85, on `--forest` 7.67; `--on-dark` on `--brand-dark` 6.43; `--forest-deep` on gold-light 9.79; white on `--forest` 13.02.
- Tap targets at least 44px high; phone layouts (900px and below) keep every action button at 44px.
- Focus is always visible: 3px ring in `--brand` (white on dark grounds and the hero, red on danger buttons); text fields get a 2px ring plus a brand border.
- Everything works from the keyboard: skip link on the landing page, dialogs trap and restore focus, focus returns to the control that opened a panel.
- Decorative art (fan notes, mascot in the lead tile, lathe work, icons) is `aria-hidden` or CSS. Errors use `role="alert"` and say "Error." in text. Status messages use a polite live region. Each screen sets its own page title.

## Copy

Truthful and plain. This is an educational project, not a real bank: no real money, cards or payments, not regulated or insured, and say so where it matters (landing hero, landing disclaimer, footer, sign-in panel). No promises of rates, safety or approval. Short sentences, the user's words, no jargon. Amounts show two decimals with no currency symbol.

## Languages and right-to-left

English, Arabic, French, Spanish and German, chosen with the language select (own-name options) in the landing header and its menu, on the sign-in and register pages, and in the app top bar (inside the menu drawer on phones). The choice is kept in `localStorage` (`pm.lang`); a first visit follows `navigator.languages`.

- Copy lives in `src/i18n/*.js`, never inline. English is the source of truth: a new key must exist in all five dictionaries, with the same `{placeholders}` (a unit test fails otherwise). Use `t(key, params)` from `useT()`/`useI18n()`; plurals are `{ one, other }` objects (Arabic needs all six forms); store messages in state as keys or English API text and translate when rendering, so a language change updates them.
- Formal register: "vous", "Sie", "usted"; Modern Standard Arabic. Keep the "educational project, not a real bank" meaning in every language. "Paper Maker" and emails are not translated.
- Digits are always Western (0-9), in Arabic too. Format through `money`, `shortDate` and `dateTime` (`ui.jsx`), which use `-u-nu-latn`; separators and month names follow the language. Amounts keep two decimals and no currency symbol.
- CSS uses logical properties only: `margin-inline-*`, `padding-inline-*`, `inset-inline-*`, `border-inline-*`, `text-align: start/end`. No `left`/`right`, `float` or `translateX` for layout; where a direction truly differs (drawer slide, sidebar rail gradient, arrows, chevrons, background positions) add an `html[dir="rtl"]` rule. Pseudo-element text comes from `--t-*` custom properties set by the provider.
- Numbers, ids and emails are `direction: ltr; unicode-bidi: isolate` (so a minus stays in front); their alignment is set by hand under `[dir="rtl"]`. Banknote graphics are not mirrored.
- Arabic uses system fonts after the Latin faces (`Segoe UI`, Tahoma, `Noto Sans Arabic`; `Noto Naskh Arabic`/`Traditional Arabic` for headings), line-height 1.65, no letter spacing and no italics. No web font is added.
- Text grows 20-40% in French, Spanish and German. Do not give buttons or labels fixed widths; check de, fr and ar at 390px and 1280px. The landing header swaps to the menu button under 1290px (1390px in French and Spanish).

## Responsive breakpoints in use

- App (`styles.css`): 900px (side nav becomes a menu drawer, tables stack into rows, 44px actions, sign-in panel becomes a banner above the form) and 720px (single-column summary tiles, smaller headings and padding, tape rows, full-width dialog buttons).
- Landing (`landing.css`): 1290px, or 1390px in French and Spanish (menu button replaces the header links), 960px (hero and split sections go single column), 860px (ledger single column), 720px (steps, roles and cards stack, full-width buttons), 480px (decorative stamp hidden).
- Checked viewports: 1440x900, 1280x800 and 390x844.

## Visual baselines

`npm run test:e2e:update` regenerates `e2e/__screenshots__`. Keep each PNG under about 250 KB: the desktop login baseline captures the form half only and desktop customer accounts the top 560px, because the lathe work compresses poorly.

## Anti-patterns (do not ship)

1. No purple or blue-violet gradients. Greens, paper and gold only; gradients are limited to the deep-note grounds.
2. No Inter or system-default look. Pair Newsreader with IBM Plex; do not add other families.
3. No generic card grid of identical icon, title and blurb tiles. Use banknote, ledger, tape and table forms.
4. No decorative gold text on light grounds, and no gold fills on light grounds. Gold is trim.
5. No new colours outside the tokens. Add or adjust a token in `:root` first, with a stated contrast reason.
6. Texture never sits behind small text at more than faint alpha; if text reads worse, lower the texture.
