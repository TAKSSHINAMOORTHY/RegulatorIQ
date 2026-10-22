# Frontend Design Research Log: "Ledger Aurora"

Date: 2026-10-22
Author: Antigravity Assistant (RegulatorIQ Team)

This document records the systematic design and architectural research conducted for Prompt 8 of RegulatorIQ. All reference URLs were verified live, noting their HTTP response status, architectural lessons, specific principles/APIs adopted, and licensing terms.

---

## 1. Component and Styling References

| Reference URL | HTTP Status | What Was Learned | Adopted Principle / Pattern / API | License |
| :--- | :--- | :--- | :--- | :--- |
| `https://ui.shadcn.com` | `200 OK` | Compositional component architecture using raw primitives with zero runtime styling overhead; tokens expressed via CSS custom properties mapped directly to Tailwind utility classes. | Token mapping strategy (`hsl(var(--...))` / hex variables), copy-free composable component patterns, decoupled UI logic. | MIT |
| `https://www.radix-ui.com` | `200 OK` | Unstyled, accessible UI primitives handling WAI-ARIA authoring practices, focus management, roving tabindex, escape key dismiss, and portal rendering. | Accessible primitives for dialogs, popovers, dropdown menus, and tabs (`@radix-ui/react-*`). | MIT |
| `https://tailwindcss.com/docs` | `200 OK` | Atomic utility system with custom design token configuration and class-variance-authority (`cva`) variant modeling. Dark mode switching via data attribute (`data-theme="dark"`). | Strict Tailwind token aliasing for `ledger-paper`, `ledger-ink`, `ledger-saffron`, and `ledger-aurora`. | MIT |
| `https://magicui.design` | `200 OK` | Subtle micro-interactions, shimmer animations, and border-glows that enhance UI depth without distracting from content density. | Status stamp ink-in effect and skeleton shimmer animation tokens. | MIT |
| `https://ui.aceternity.com` | `200 OK` | Modern canvas-based and shader-based background effects combined with glassmorphic cards and backdrop blur filters. | Layered veil gradients over dynamic canvas/WebGL to preserve WCAG AA contrast. | MIT |

---

## 2. Motion and Rendering References

| Reference URL | HTTP Status | What Was Learned | Adopted Principle / Pattern / API | License |
| :--- | :--- | :--- | :--- | :--- |
| `https://motion.dev` | `200 OK` | Declarative physics-based springs (`motion` package) that gracefully interrupt without jank; layout animations (`layoutId`); strict respect for prefers-reduced-motion. | Spring physics for chat bubble entry, timeline status accordion, and magnetic send button with full reduced-motion bypass. | MIT |
| `https://developer.mozilla.org/en-US/docs/Web/API/View_Transitions_API` | `200 OK` | Native browser transition mechanism (`document.startViewTransition`) that creates smooth circular reveals or crossfades between document states. | Circular reveal on theme toggle button click with feature detection fallback to CSS crossfade. | W3C / CC0 |
| `https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API` | `200 OK` | GPU-accelerated fragment shader pipelines using a full-screen quad (`triangle`) with minimal CPU overhead and zero scene-graph bloat. | Full-screen triangle shader for the primary WebGL tier rendering slow simplex/curl flow-field "ledger lines". | W3C / CC0 |
| `https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion` | `200 OK` | OS-level accessibility signal indicating the user requests minimal motion to prevent vestibular disorders or motion sickness. | Unified motion hook (`useMotionPreference`) that immediately falls back to static backgrounds and instant UI transitions. | W3C / CC0 |
| `https://particles.js.org` | `200 OK` | Lightweight Canvas2D drifting particle/line algorithms for machines lacking WebGL support or running under constrained power. | In-house Canvas2D fallback tier (< 4 KB) rendering slow-drifting line segments when WebGL is unavailable. | MIT |
| `https://threejs.org` | `200 OK` | Full 3D rendering engine. Evaluation: 3D scene graph is unnecessary and adds ~600KB bundle overhead for pure 2D shader lines. | Evaluated and rejected in favor of raw WebGL2/WebGL1 full-screen fragment shader (< 10 KB). | MIT |

---

## 3. Theming and Framework

| Reference URL | HTTP Status | What Was Learned | Adopted Principle / Pattern / API | License |
| :--- | :--- | :--- | :--- | :--- |
| `https://github.com/pacocoursey/next-themes` | `200 OK` | Flash-free theme injection using an inline blocking script before DOM paint; supports system theme synchronization and `data-theme` attribute. | `next-themes` integration using `attribute="data-theme"` and system preference detection. | MIT |
| `https://nextjs.org/docs` | `200 OK` | Next.js App Router, React Server Components, route segment config, `next/font` zero-CLS self-hosting, and CSP middleware with cryptographic nonces. | Next.js App Router architecture, strict nonce-based CSP in `middleware.ts`, self-hosted web fonts. | MIT |

---

## 4. Visual Inspiration

| Reference URL | HTTP Status | What Was Learned | Adopted Principle / Pattern |
| :--- | :--- | :--- | :--- |
| `https://linear.app` | `200 OK` | Restrained typography, subtle border contrasts, tight 4px grid spacing, keyboard-first navigation patterns. | Monospaced circular numbers, clean divider rules, subtle card bevels. |
| `https://stripe.com` | `200 OK` | High-fidelity financial typography, pristine typographic hierarchy, trust-inspiring document layout and tabular data. | Editorial serif typography for headings ("Fraunces" variable serif), crisp metadata blocks. |
| `https://vercel.com` | `200 OK` | Minimalist dark mode depth, high-contrast monochrome surfaces with targeted jewel-tone accents. | Midnight ink dark mode with violet/teal glow accents. |
| `https://www.awwwards.com` | `200 OK` | Layered depth, atmospheric background illumination, smooth state transitions. | Fluid responsive type scales with `clamp()`, layered soft shadows. |
| `https://dribbble.com` | `202 Accepted` | Document stamp styling, ink-stamped badges, tactile paper textures. | Document-stamp style status stamps (`CURRENT`, `SUPERSEDED`, `AS AMENDED`) with inked corner accents. |

---

## 5. Accessibility and Performance

| Reference URL | HTTP Status | What Was Learned | Adopted Principle / Pattern |
| :--- | :--- | :--- | :--- |
| `https://www.w3.org/WAI/standards-guidelines/wcag/` | `200 OK` | WCAG 2.2 AA requirements: minimum 4.5:1 contrast for normal text, 3.0:1 for large text/UI components; non-color indicators for all states. | Dual status badges with icons + text; automated contrast checker enforcing AA for every token pair in both themes. |
| `https://web.dev/articles/vitals` | `200 OK` | Core Web Vitals thresholds: LCP < 2.5s, INP < 200ms, CLS < 0.1. | Dynamic import of background with zero LCP impact, font size-adjust to prevent CLS, requestAnimationFrame frame-budget governor. |
