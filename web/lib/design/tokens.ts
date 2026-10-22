/**
 * Ledger Aurora Design Tokens
 * Mirrored from web/styles/tokens.css for programmatic access, contrast testing, and type safety.
 */

export interface ColorPalette {
  bg: string;
  surface: string;
  surface2: string;
  ink: string;
  muted: string;
  line: string;
  accent: string;
  accentText: string;
  accent2: string;
  glowViolet: string;
  success: string;
  warning: string;
  danger: string;
  focusRing: string;
  veilBg: string;
  glassBg: string;
  glassBorder: string;
}

export const lightPalette: ColorPalette = {
  bg: "#FAF6EE",
  surface: "#FFFFFF",
  surface2: "#F3EDE0",
  ink: "#1B1A17",
  muted: "#6B665C",
  line: "#E7DFCF",
  accent: "#C26100",
  accentText: "#92400E",
  accent2: "#0F766E",
  glowViolet: "#6D28D9",
  success: "#166534",
  warning: "#9A3412",
  danger: "#B91C1C",
  focusRing: "#2563EB",
  veilBg: "rgba(250, 246, 238, 0.82)",
  glassBg: "rgba(255, 255, 255, 0.75)",
  glassBorder: "rgba(231, 223, 207, 0.65)",
};

export const darkPalette: ColorPalette = {
  bg: "#0A0F1E",
  surface: "#121A2E",
  surface2: "#18233D",
  ink: "#EDEFF5",
  muted: "#98A2B8",
  line: "#243049",
  accent: "#F5B14C",
  accentText: "#F5B14C",
  accent2: "#2DD4BF",
  glowViolet: "#7C5CFF",
  success: "#4ADE80",
  warning: "#FBBF24",
  danger: "#F87171",
  focusRing: "#60A5FA",
  veilBg: "rgba(10, 15, 30, 0.82)",
  glassBg: "rgba(18, 26, 46, 0.75)",
  glassBorder: "rgba(36, 48, 73, 0.7)",
};

export const radii = {
  sm: "10px",
  md: "16px",
  lg: "24px",
};

export const spacingGrid = 4; // 4px baseline grid
