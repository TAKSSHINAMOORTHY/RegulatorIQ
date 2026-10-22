# Ledger Aurora Design System

**System Version:** 1.0.0  
**Status:** Active & WCAG 2.2 AA Certified  
**Visual Metaphor:** An editorial, authoritative regulatory ledger meets a calm aurora borealis glow. Light mode evokes tactile paper, dark ink, and warm saffron accents; dark mode embodies midnight ink with luminous teal and violet aurora lines.

---

## 1. Visual & Typography Foundations

### Fonts (Zero CLS, Build-time Self-Hosted)
- **Headings & Editorial Display:** `Fraunces` (variable serif, optical sizing, fluid `clamp()`)
- **Body & Controls:** `Inter` (geometric sans-serif, high legibility, strict vertical rhythm)
- **Identifiers & Numeric Data:** `JetBrains Mono` (circular numbers, dates, paragraph refs, tabular figures)

### Spacing Grid
Based on a strict 4px grid (`4px`, `8px`, `12px`, `16px`, `24px`, `32px`, `48px`, `64px`). All cards, gaps, and padding align to multiples of 4px.

### Radii Hierarchy
- Small (`--radius-sm: 10px`): badges, citation chips, buttons, inputs.
- Medium (`--radius-md: 16px`): message cards, popovers, source cards.
- Large (`--radius-lg: 24px`): modal dialogs, drawers, bottom sheets.

---

## 2. Color Palettes & Accessibility Ratios

Every color combination in both themes has been verified with `scripts/check_contrast.ts` and meets or exceeds WCAG 2.2 AA (minimum 4.5:1 for body copy; minimum 3.0:1 for large text and UI components).

### Light Theme ("Paper & Saffron")
- Background: `#FAF6EE` (Warm paper)
- Surface: `#FFFFFF` (Crisp paper)
- Surface-2: `#F3EDE0` (Tinted parchment)
- Ink / Text: `#1B1A17` (Contrast 16.14:1)
- Muted: `#6B665C` (Contrast 5.29:1)
- Line: `#E7DFCF`
- Accent (UI): `#C26100` (Contrast 3.89:1)
- Accent Text: `#92400E` (Contrast 6.58:1)
- Accent 2 (Teal): `#0F766E` (Contrast 5.08:1)
- Success: `#166534` (Contrast 6.61:1)
- Warning: `#9A3412` (Contrast 6.78:1)
- Danger: `#B91C1C` (Contrast 6.00:1)
- Focus Ring: `#2563EB` (Contrast 4.79:1)

### Dark Theme ("Midnight Ink")
- Background: `#0A0F1E` (Deep space obsidian)
- Surface: `#121A2E` (Navy slate)
- Surface-2: `#18233D` (Indigo tinted surface)
- Ink / Text: `#EDEFF5` (Contrast 16.61:1)
- Muted: `#98A2B8` (Contrast 7.45:1)
- Line: `#243049`
- Accent / Glow: `#F5B14C` (Contrast 10.25:1)
- Accent 2 (Teal): `#2DD4BF` (Contrast 10.26:1)
- Glow Violet: `#7C5CFF` (Contrast 4.39:1)
- Success: `#4ADE80` (Contrast 10.96:1)
- Warning: `#FBBF24` (Contrast 11.44:1)
- Danger: `#F87171` (Contrast 6.90:1)
- Focus Ring: `#60A5FA` (Contrast 7.51:1)

---

## 3. Signature Details

1. **Ruled Ledger Lines:** Subtle background grid lines evoking banking ledgers, rendered dynamically or as static SVG accents.
2. **Document-Stamp Status Badges:** Monospaced, boxed stamps with an inked corner accent representing regulatory validity (`CURRENT`, `SUPERSEDED`, `AS AMENDED`).
3. **Tab-Shaped Citation Chips:** Small clickable tabs with a bottom border indicator linking directly to source cards.
4. **Faint Underlined Monospace Identifiers:** Circular reference numbers and notification tags styled with subtle dashed or hairline underlines.
5. **View Transition Circular Reveal:** Smooth radial wipe from the toggle button during theme switches.

---

## 4. Motion Principles

- **Physics-Based Springs:** Interfaces feel physical and snappy; message cards enter with slight vertical spring displacement (8px, 180ms).
- **Reduced Motion First:** All animations read `useMotionPreference()`. If `prefers-reduced-motion` is active or the user toggles Reduce Motion, all movement is stripped in favor of clean opacity transitions.
- **Budget Compliance:** Only `transform` and `opacity` are animated to ensure continuous 60fps rendering without layout recalculations.

---

## 5. Do's and Don'ts

| Do | Don't |
| :--- | :--- |
| Use official status stamps with both icon and text | Never rely on color alone to indicate superseded status |
| Self-host all fonts through Next.js build-time bundling | Never load fonts or scripts from Google Fonts / CDNs at runtime |
| Verify external links point strictly to `rbi.org.in` | Never create active hyperlinks to arbitrary third-party domains |
| Provide progressive disclosure for long regulatory quotes | Never overwhelm the chat window with untruncated circulars |
| Respect system dark mode and user overrides | Never flash unstyled or wrong-theme backgrounds on page reload |
