export type BrandPalette = Record<string, string>;

export type BrandFonts = {
  display?: string;
  body?: string;
  mono?: string;
  tagline?: string;
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
  fonts: { display: "Newsreader", body: "Geist", mono: "JetBrains Mono", tagline: "Instrument Serif" },
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
