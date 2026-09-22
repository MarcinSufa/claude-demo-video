export type BrandPalette = Record<string, string>;

export type BrandFonts = {
  display?: string;
  body?: string;
  mono?: string;
  tagline?: string;
  /** apply-brand.py's own Google Fonts css2 link builder (FONT_SPECS axis
   * table), reused as-is -- plan-scenes.py extracts the URL it already
   * rendered into subs.google_fonts_link rather than re-picking font axes
   * here. null/undefined when brand.yaml has no typography configured. */
  google_fonts_url?: string | null;
};

export type BrandProps = {
  palette: BrandPalette;
  fonts: BrandFonts;
  project_name: string;
  project_url: string;
};

/** plan-scenes.py always sends these; fall back only for a scene rendered
 * standalone (e.g. `remotion render` run by hand without --props). */
export const defaultBrand: BrandProps = {
  palette: { bg: "#0a0705", fg: "#dcd7cf", accent: "#dbaf71" },
  fonts: {
    display: "Newsreader", body: "Geist", mono: "JetBrains Mono", tagline: "Instrument Serif",
    google_fonts_url: null,
  },
  project_name: "MyProduct",
  project_url: "myproduct.com",
};

export function withBrandDefaults(brand: Partial<BrandProps> | undefined): BrandProps {
  return {
    palette: { ...defaultBrand.palette, ...(brand?.palette ?? {}) },
    fonts: { ...defaultBrand.fonts, ...(brand?.fonts ?? {}) },
    project_name: brand?.project_name ?? defaultBrand.project_name,
    project_url: brand?.project_url ?? defaultBrand.project_url,
  };
}
