# Ledger Aurora Contrast & Accessibility Report (WCAG 2.2 AA)

**Date:** 2026-10-22T09:10:57.084Z
**Status:** PASSED (All pairs meet WCAG AA requirements)

This report verifies contrast ratios for all text, UI element, and glass surface token pairs in both light ('Paper & Saffron') and dark ('Midnight Ink') themes. Body text requires >= 4.5:1; UI components and large text require >= 3.0:1.

## Summary of Adjustments

- In light mode, `accent-text` is tuned to `#92400E` to guarantee >= 4.5:1 body text contrast on all surfaces including `surface-2` and glass (base saffron `#D97706` is reserved for UI badges and border accents where 3.0:1 applies).
- In dark mode, `glow-violet` is treated as a UI/glow element (3.0:1 requirement) while `accent-2` (`#2DD4BF`) and `accent-text` (`#F5B14C`) provide exceptional 8:1 - 10:1 body text contrast.

## Detailed Test Matrix

| Theme | Foreground | Hex | Background | Hex | Type | Required | Actual Ratio | Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| light | ink | `#1B1A17` | bg | `#FAF6EE` | body | 4.5:1 | **16.14:1** | PASS |
| light | muted | `#6B665C` | bg | `#FAF6EE` | body | 4.5:1 | **5.29:1** | PASS |
| light | accent-text | `#92400E` | bg | `#FAF6EE` | body | 4.5:1 | **6.58:1** | PASS |
| light | accent-2 | `#0F766E` | bg | `#FAF6EE` | body | 4.5:1 | **5.08:1** | PASS |
| light | success | `#166534` | bg | `#FAF6EE` | body | 4.5:1 | **6.61:1** | PASS |
| light | warning | `#9A3412` | bg | `#FAF6EE` | body | 4.5:1 | **6.78:1** | PASS |
| light | danger | `#B91C1C` | bg | `#FAF6EE` | body | 4.5:1 | **6:1** | PASS |
| light | accent (UI) | `#C26100` | bg | `#FAF6EE` | ui | 3:1 | **3.89:1** | PASS |
| light | focus-ring (UI) | `#2563EB` | bg | `#FAF6EE` | ui | 3:1 | **4.79:1** | PASS |
| light | ink | `#1B1A17` | surface | `#FFFFFF` | body | 4.5:1 | **17.4:1** | PASS |
| light | muted | `#6B665C` | surface | `#FFFFFF` | body | 4.5:1 | **5.71:1** | PASS |
| light | accent-text | `#92400E` | surface | `#FFFFFF` | body | 4.5:1 | **7.09:1** | PASS |
| light | accent-2 | `#0F766E` | surface | `#FFFFFF` | body | 4.5:1 | **5.47:1** | PASS |
| light | success | `#166534` | surface | `#FFFFFF` | body | 4.5:1 | **7.13:1** | PASS |
| light | warning | `#9A3412` | surface | `#FFFFFF` | body | 4.5:1 | **7.31:1** | PASS |
| light | danger | `#B91C1C` | surface | `#FFFFFF` | body | 4.5:1 | **6.47:1** | PASS |
| light | accent (UI) | `#C26100` | surface | `#FFFFFF` | ui | 3:1 | **4.2:1** | PASS |
| light | focus-ring (UI) | `#2563EB` | surface | `#FFFFFF` | ui | 3:1 | **5.17:1** | PASS |
| light | ink | `#1B1A17` | surface-2 | `#F3EDE0` | body | 4.5:1 | **14.92:1** | PASS |
| light | muted | `#6B665C` | surface-2 | `#F3EDE0` | body | 4.5:1 | **4.89:1** | PASS |
| light | accent-text | `#92400E` | surface-2 | `#F3EDE0` | body | 4.5:1 | **6.08:1** | PASS |
| light | accent-2 | `#0F766E` | surface-2 | `#F3EDE0` | body | 4.5:1 | **4.69:1** | PASS |
| light | success | `#166534` | surface-2 | `#F3EDE0` | body | 4.5:1 | **6.11:1** | PASS |
| light | warning | `#9A3412` | surface-2 | `#F3EDE0` | body | 4.5:1 | **6.26:1** | PASS |
| light | danger | `#B91C1C` | surface-2 | `#F3EDE0` | body | 4.5:1 | **5.55:1** | PASS |
| light | accent (UI) | `#C26100` | surface-2 | `#F3EDE0` | ui | 3:1 | **3.6:1** | PASS |
| light | focus-ring (UI) | `#2563EB` | surface-2 | `#F3EDE0` | ui | 3:1 | **4.43:1** | PASS |
| light | ink | `#1B1A17` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **17.12:1** | PASS |
| light | muted | `#6B665C` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **5.61:1** | PASS |
| light | accent-text | `#92400E` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **6.97:1** | PASS |
| light | accent-2 | `#0F766E` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **5.38:1** | PASS |
| light | success | `#166534` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **7.01:1** | PASS |
| light | warning | `#9A3412` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **7.19:1** | PASS |
| light | danger | `#B91C1C` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | body | 4.5:1 | **6.36:1** | PASS |
| light | accent (UI) | `#C26100` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | ui | 3:1 | **4.13:1** | PASS |
| light | focus-ring (UI) | `#2563EB` | glass (over bg) | `rgba(255, 255, 255, 0.75)` | ui | 3:1 | **5.08:1** | PASS |
| dark | ink | `#EDEFF5` | bg | `#0A0F1E` | body | 4.5:1 | **16.61:1** | PASS |
| dark | muted | `#98A2B8` | bg | `#0A0F1E` | body | 4.5:1 | **7.45:1** | PASS |
| dark | accent-text | `#F5B14C` | bg | `#0A0F1E` | body | 4.5:1 | **10.25:1** | PASS |
| dark | accent-2 | `#2DD4BF` | bg | `#0A0F1E` | body | 4.5:1 | **10.26:1** | PASS |
| dark | glow-violet | `#7C5CFF` | bg | `#0A0F1E` | ui | 3:1 | **4.39:1** | PASS |
| dark | success | `#4ADE80` | bg | `#0A0F1E` | body | 4.5:1 | **10.96:1** | PASS |
| dark | warning | `#FBBF24` | bg | `#0A0F1E` | body | 4.5:1 | **11.44:1** | PASS |
| dark | danger | `#F87171` | bg | `#0A0F1E` | body | 4.5:1 | **6.9:1** | PASS |
| dark | focus-ring (UI) | `#60A5FA` | bg | `#0A0F1E` | ui | 3:1 | **7.51:1** | PASS |
| dark | ink | `#EDEFF5` | surface | `#121A2E` | body | 4.5:1 | **15.06:1** | PASS |
| dark | muted | `#98A2B8` | surface | `#121A2E` | body | 4.5:1 | **6.76:1** | PASS |
| dark | accent-text | `#F5B14C` | surface | `#121A2E` | body | 4.5:1 | **9.3:1** | PASS |
| dark | accent-2 | `#2DD4BF` | surface | `#121A2E` | body | 4.5:1 | **9.3:1** | PASS |
| dark | glow-violet | `#7C5CFF` | surface | `#121A2E` | ui | 3:1 | **3.98:1** | PASS |
| dark | success | `#4ADE80` | surface | `#121A2E` | body | 4.5:1 | **9.94:1** | PASS |
| dark | warning | `#FBBF24` | surface | `#121A2E` | body | 4.5:1 | **10.37:1** | PASS |
| dark | danger | `#F87171` | surface | `#121A2E` | body | 4.5:1 | **6.26:1** | PASS |
| dark | focus-ring (UI) | `#60A5FA` | surface | `#121A2E` | ui | 3:1 | **6.81:1** | PASS |
| dark | ink | `#EDEFF5` | surface-2 | `#18233D` | body | 4.5:1 | **13.56:1** | PASS |
| dark | muted | `#98A2B8` | surface-2 | `#18233D` | body | 4.5:1 | **6.09:1** | PASS |
| dark | accent-text | `#F5B14C` | surface-2 | `#18233D` | body | 4.5:1 | **8.37:1** | PASS |
| dark | accent-2 | `#2DD4BF` | surface-2 | `#18233D` | body | 4.5:1 | **8.38:1** | PASS |
| dark | glow-violet | `#7C5CFF` | surface-2 | `#18233D` | ui | 3:1 | **3.59:1** | PASS |
| dark | success | `#4ADE80` | surface-2 | `#18233D` | body | 4.5:1 | **8.95:1** | PASS |
| dark | warning | `#FBBF24` | surface-2 | `#18233D` | body | 4.5:1 | **9.34:1** | PASS |
| dark | danger | `#F87171` | surface-2 | `#18233D` | body | 4.5:1 | **5.64:1** | PASS |
| dark | focus-ring (UI) | `#60A5FA` | surface-2 | `#18233D` | ui | 3:1 | **6.13:1** | PASS |
| dark | ink | `#EDEFF5` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **15.51:1** | PASS |
| dark | muted | `#98A2B8` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **6.96:1** | PASS |
| dark | accent-text | `#F5B14C` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **9.57:1** | PASS |
| dark | accent-2 | `#2DD4BF` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **9.58:1** | PASS |
| dark | glow-violet | `#7C5CFF` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | ui | 3:1 | **4.1:1** | PASS |
| dark | success | `#4ADE80` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **10.23:1** | PASS |
| dark | warning | `#FBBF24` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **10.68:1** | PASS |
| dark | danger | `#F87171` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | body | 4.5:1 | **6.44:1** | PASS |
| dark | focus-ring (UI) | `#60A5FA` | glass (over bg) | `rgba(18, 26, 46, 0.75)` | ui | 3:1 | **7.01:1** | PASS |
