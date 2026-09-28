// timeline.json (SPEC.md 3.7) = inputProps of the "Main" composition.
// settings.default.json (SPEC.md 3.8 + v2 diff A1-A7) = timeline.style.
//
// Backward compatibility: every v2 key is optional in the incoming JSON. resolveStyle() merges
// timeline.style over DEFAULT_STYLE one level deep, so an old (v1) settings.json without the
// new keys still renders with the v2 defaults for those keys.

export type CaptionCue = {start: number; end: number; text: string};
export type HeadingCue = {start: number; end: number; text: string};
export type ScreenSegment = {start: number; end: number};
export type BrollKind = 'vertical' | 'photo' | 'web';
export type BrollCue = {
  start: number;
  end: number;
  file: string;
  kind: BrollKind;
  /** optional page background color for kind=web (else sampled from the image's top-left pixel) */
  bg?: string;
};

export type CaptionStyle = {
  font: string;
  weight: number;
  size_ratio: number;
  bottom_ratio: number;
  color: string;
  stroke_color: string;
  stroke_ratio: number;
  /** legacy (v1). true + style "outline" => outline gets a shadow too. Ignored for style "shadow". */
  shadow: boolean;
  /** v2 A4: "shadow" (default) = no outline, drop shadow only. "outline" = black stroke + shadow. */
  style: 'shadow' | 'outline';
  /** drop shadow (px @1080p, scaled with height) */
  shadow_offset_px: number;
  shadow_blur_px: number;
  shadow_alpha: number;
  max_chars: number;
  min_dur: number;
  max_dur: number;
  gap_fill: number;
  punctuation: boolean;
  [k: string]: unknown;
};

export type HeadingStyle = {
  position: 'top-left' | 'top-right';
  /** "skew": parallelogram, the whole band incl. text is skewX'ed (pseudo italic). "rounded": upright, radius 20px, no anim. */
  shape: 'skew' | 'rounded';
  skew_deg: number;
  band_color: string;
  text_color: string;
  size_ratio: number;
  margin_x_ratio: number;
  margin_y_ratio: number;
  /** legacy ratio paddings (v1). Used only when pad_x_px / pad_y_px are absent. */
  pad_x_ratio?: number;
  pad_y_ratio?: number;
  /** v2 A3: px @1080p (scaled with height) */
  pad_x_px: number;
  pad_y_px: number;
  /** v2 A3: 0.25s slide-in from the band's side; out = instant */
  anim: 'slide' | 'fade' | 'none';
  anim_in: number;
  /** v2 A3: keep the band visible while a screen segment is on (default true) */
  show_during_screen: boolean;
  /** radius (px @1080p) for shape "rounded" */
  rounded_radius_px: number;
  [k: string]: unknown;
};

export type WipeStyle = {
  position: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  size: 'standard' | 'small';
  diameter_ratio: number;
  small_ratio: number;
  /** legacy (v1) corner margin. Used only when center_x_ratio/center_y_ratio are absent. */
  margin_ratio?: number;
  /** v2 A1: circle centre as a fraction of W / H for the *bottom-left* position; mirrored for the others. */
  center_x_ratio: number;
  center_y_ratio: number;
  /** v2 A1: fade-in seconds at the start of each wipe segment */
  fade: number;
  border: boolean;
  focus: {x: number; y: number};
  [k: string]: unknown;
};

export type ScreenPreset = 'author' | 'takkatw' | 'custom';

export type ScreenStyle = {
  layout: 'inset' | 'full';
  bg: string;
  /**
   * v2 A2. "author" (default): W*0.875 wide, top H*0.028, left W*0.092 (NOT centred), radius 12px.
   * "takkatw": W*0.743 wide, top 40px, centred, radius 0.
   * "custom": use width_ratio / top_ratio / left_ratio / radius_px (or legacy radius_ratio) below.
   */
  preset: ScreenPreset;
  width_ratio?: number;
  top_ratio?: number;
  /** left edge as a fraction of W; omit => centred */
  left_ratio?: number;
  radius_px?: number;
  /** legacy (v1) */
  radius_ratio?: number;
  [k: string]: unknown;
};

export type VerticalSourceStyle = {
  /** v2 A7: default "navy" (#101627). "blur" = frosted copy of the source. */
  background: 'blur' | 'navy';
  blur_px: number;
  dim: number;
  [k: string]: unknown;
};

export type BrollStyle = {
  style: 'frosted-card';
  speaker_width_ratio: number;
  card_radius_ratio: number;
  /** v2 A5: vertical card radius in px @1080p (30) */
  vertical_radius_px: number;
  /** v2 A5: vertical card centre (fractions of W/H) and max height (fraction of H) */
  vertical_center_x_ratio: number;
  vertical_center_y_ratio: number;
  vertical_max_h_ratio: number;
  /** slow zoom 1.00 -> zoom_to; v2 A5: applied to kind=photo only */
  zoom_to: number;
  /** legacy (v1) fade seconds. Used when `duration` is absent. */
  fade?: number;
  /** v2 A6: whole-layout dissolve between camera layout and B-roll layout */
  transition: 'dissolve' | 'none';
  duration: number;
  glass_white: number;
  blur_px: number;
  [k: string]: unknown;
};

export type Style = {
  version?: string;
  resolution?: string;
  fps?: number;
  caption: CaptionStyle;
  heading: HeadingStyle;
  wipe: WipeStyle;
  screen: ScreenStyle;
  vertical_source: VerticalSourceStyle;
  broll: BrollStyle;
  // cuts / audio / output are consumed by the python side, ignored here
  [k: string]: unknown;
};

export type Timeline = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  /** relative to public/work/ (e.g. "cut.mp4") or an absolute http(s) URL */
  video: string;
  screen: string | null;
  sourceAspect: '16:9' | '9:16';
  /** aspect of the screen recording, default 16:9 (used to size the inset box) */
  screenAspect?: string;
  style: Partial<Style>;
  captions: CaptionCue[];
  headings: HeadingCue[];
  screenSegments: ScreenSegment[];
  broll: BrollCue[];
};

export const NAVY = '#101627';

export const SCREEN_PRESETS: Record<
  Exclude<ScreenPreset, 'custom'>,
  {width_ratio: number; top_ratio: number; left_ratio?: number; radius_px: number}
> = {
  // measured on the author's (shupeiman) 1080p reference: box x 177..1857 (W*0.092..0.967), top 30px
  author: {width_ratio: 0.875, top_ratio: 0.028, left_ratio: 0.092, radius_px: 12},
  // takkatw reference: 1427px wide, top 40px, centred, square corners
  takkatw: {width_ratio: 0.743, top_ratio: 40 / 1080, radius_px: 0},
};

export const DEFAULT_STYLE: Style = {
  version: 'v2',
  resolution: '1080p',
  fps: 30,
  caption: {
    font: 'Noto Sans JP',
    weight: 900,
    size_ratio: 0.048,
    bottom_ratio: 0.069,
    color: '#FFFFFF',
    stroke_color: '#000000',
    stroke_ratio: 0.004,
    shadow: true,
    style: 'shadow',
    shadow_offset_px: 2,
    shadow_blur_px: 5,
    shadow_alpha: 0.5,
    max_chars: 18,
    min_dur: 0.6,
    max_dur: 4.0,
    gap_fill: 0.6,
    punctuation: false,
  },
  heading: {
    position: 'top-left',
    shape: 'skew',
    skew_deg: -8.5,
    band_color: '#FFFFFF',
    text_color: '#182028',
    size_ratio: 0.041,
    margin_x_ratio: 0.045,
    margin_y_ratio: 0.055,
    pad_x_px: 32,
    pad_y_px: 20,
    anim: 'slide',
    anim_in: 0.25,
    show_during_screen: true,
    rounded_radius_px: 20,
  },
  wipe: {
    position: 'bottom-left',
    size: 'standard',
    diameter_ratio: 0.22,
    small_ratio: 0.16,
    center_x_ratio: 0.085,
    center_y_ratio: 0.72,
    fade: 0.2,
    border: false,
    focus: {x: 0.5, y: 0.35},
  },
  screen: {
    layout: 'inset',
    bg: NAVY,
    preset: 'author',
  },
  vertical_source: {background: 'navy', blur_px: 40, dim: 0.35},
  broll: {
    style: 'frosted-card',
    speaker_width_ratio: 0.4,
    card_radius_ratio: 0.028,
    vertical_radius_px: 30,
    vertical_center_x_ratio: 0.7,
    vertical_center_y_ratio: 0.51,
    vertical_max_h_ratio: 0.62,
    zoom_to: 1.06,
    transition: 'dissolve',
    duration: 0.33,
    glass_white: 0.7,
    blur_px: 40,
  },
};

/** deep-merge timeline.style over DEFAULT_STYLE (one level of nesting is enough for this schema) */
export const resolveStyle = (partial?: Partial<Style> | null): Style => {
  const out: Record<string, unknown> = {...DEFAULT_STYLE};
  if (!partial) return out as Style;
  for (const [k, v] of Object.entries(partial)) {
    const base = (DEFAULT_STYLE as Record<string, unknown>)[k];
    if (v && typeof v === 'object' && !Array.isArray(v) && base && typeof base === 'object') {
      const merged: Record<string, unknown> = {...(base as object)};
      for (const [kk, vv] of Object.entries(v as Record<string, unknown>)) {
        if (vv !== undefined && vv !== null) merged[kk] = vv;
      }
      out[k] = merged;
    } else if (v !== undefined && v !== null) {
      out[k] = v;
    }
  }
  return out as Style;
};

/** px value specified at 1080p, scaled to the composition height (4K => x2) */
export const px = (v: number, height: number): number => (v * height) / 1080;
