# yt-auto-edit / remotion (v2)

Remotion v4 renderer for `timeline.json` (SPEC.md 3.7). Composites the "しゅうへい流" look
(SPEC.md 2.1-2.6 + v2 diff A1-A7) over the already-cut camera video and writes a 16:9 H.264 mp4.

```
remotion/
  package.json, tsconfig.json, remotion.config.ts   # h264 / crf18 / yuv420p bt709 / aac 192k
  render_timeline.sh                                 # thin wrapper (see below)
  src/index.ts        registerRoot
  src/Root.tsx        <Composition id="Main"> ; calculateMetadata takes width/height/fps/durationInFrames from props
  src/Main.tsx        layer stack (+ heading.show_during_screen)
  src/types.ts        Timeline / Style types + DEFAULT_STYLE (= settings.default.json) + resolveStyle() + SCREEN_PRESETS
  src/media.ts        resolveMedia(): relative path -> staticFile("work/<path>")
  src/font.ts         loads public/fonts/NotoSansJP[wght].ttf (FontFace + delayRender)
  src/components/
    Background.tsx    camera full-frame (16:9) or full-height centred over navy (default) / blur (9:16). The only UNMUTED video.
    ScreenInset.tsx   navy #101627 + screen recording; preset author (W*0.875, top H*0.028, left W*0.092, r12) | takkatw | custom
    CircleWipe.tsx    circular face crop of the camera; default bottom-left, centre (W*0.085, H*0.72), d=H*0.22 (small 0.16), 0.2 s fade-in
    BrollCard.tsx     v5 frosted-glass card (vertical static / photo zoom / web), whole-layout dissolve 0.33 s
    HeadingBand.tsx   top-left white band, whole band skewX(-8.5deg) (text leans too) or rounded (20px, upright, #000)
    Caption.tsx       white 1-line caption, weight 900, H*0.048, bottom H*0.069; style shadow (default) | outline
  public/fonts/NotoSansJP[wght].ttf   variable font (wght 100-900)
  public/work/        -> symlink to OUT/work (render.sh) ; here: runs/pretest/work (v2 smoke data)
  out/                v2smoke.mp4 + v2smoke_NN.png + measure_v2.py (OpenCV checks) ; v1 smoke.* kept
```

## Render

```bash
cd remotion
npm install            # once (remotion 4.0.529, @remotion/cli, @remotion/media-utils, react 19, typescript)

# generic
npx remotion render src/index.ts Main /path/to/out.mp4 --props=public/work/timeline.json --color-space=bt709

# this container (no GPU, Playwright Chromium): the full `chrome` binary no longer supports old headless
# mode, so pass the headless shell; on macOS omit --browser-executable/--gl (Remotion downloads its own).
npx remotion render src/index.ts Main out/v2smoke.mp4 --props=public/work/timeline.json \
  --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell \
  --concurrency=3 --gl=swangle --color-space=bt709

# wrapper (env: REMOTION_BROWSER, REMOTION_GL, REMOTION_CONCURRENCY)
REMOTION_BROWSER=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell \
  ./render_timeline.sh public/work/timeline.json out/v2smoke.mp4

# single frame (fast, ~7 s) for checking a style change
npx remotion still src/index.ts Main out/f60.png --frame=60 --props=public/work/timeline.json \
  --browser-executable=... --gl=swangle

# 1 frame per second for QC
ffmpeg -i out/v2smoke.mp4 -vf fps=1 -start_number 0 out/v2smoke_%02d.png
```

`npx remotion studio src/index.ts` opens the interactive preview (loads defaultProps; paste timeline.json in the props panel).

## Props schema (`timeline.json` = inputProps of "Main")

```jsonc
{
  "fps": 30, "width": 1920, "height": 1080,
  "durationInFrames": 240,              // if missing/0 -> taken from the cut video length
  "video": "cut.mp4",                   // camera+audio, already cut. relative => public/work/<path>; http(s) URLs pass through
  "screen": "screen_cut.mp4" | null,    // screen recording, SAME timeline as cut.mp4 (frame N of screen == frame N of video)
  "sourceAspect": "16:9" | "9:16",      // 9:16 -> full-height centred + navy/blur background
  "screenAspect": "16:9",               // optional, sizes the inset box (default 16:9)
  "style": { ...subset of settings.json... },   // deep-merged over DEFAULT_STYLE (src/types.ts) – only override what you need
  "captions":       [{"start": 0.2, "end": 2.4, "text": "もうめちゃくちゃ大後悔です"}],
  "headings":       [{"start": 0.5, "end": 7.6, "text": "実物はこんなに小さい"}],
  "screenSegments": [{"start": 2.0, "end": 4.6}],
  "broll":          [{"start": 5.0, "end": 7.6, "file": "shot.png", "kind": "vertical" | "photo" | "web", "bg": "#fff"?}]
}
```
All times are seconds on the OUTPUT timeline. Style keys used here: `caption`, `heading`, `wipe`, `screen`,
`vertical_source`, `broll`. `cuts` / `audio` / `output` are ignored by the renderer.

Layer order: Background(camera, audio) -> screenSegments (ScreenInset + CircleWipe) -> broll (dissolved) -> HeadingBand -> Caption.

## v2 style keys (defaults in `src/types.ts` DEFAULT_STYLE; px values are @1080p and scale with height, so 4K = x2)

| group | key | default | note |
|---|---|---|---|
| caption | `style` | `"shadow"` | `"shadow"` = no outline, drop shadow only. `"outline"` = black stroke `stroke_ratio` (0.004H) + shadow |
| caption | `shadow_offset_px` / `shadow_blur_px` / `shadow_alpha` | 2 / 5 / 0.5 | text-shadow `2px 2px 5px rgba(0,0,0,.5)` |
| caption | `size_ratio` / `bottom_ratio` / `min_dur` | 0.048 / 0.069 / 0.6 | glyph box bottom sits 0.069H above the frame bottom |
| heading | `skew_deg` | -8.5 | applied to the whole band **container** (text leans with it) |
| heading | `pad_x_px` / `pad_y_px` | 32 / 20 | band height = 0.041H*1.12 + 40 ≈ 0.083H. Legacy `pad_*_ratio` used only if the px keys are absent |
| heading | `text_color` | `#182028` | |
| heading | `anim` / `anim_in` | `"slide"` / 0.25 | in = slide from the band's side; **out = instant** |
| heading | `show_during_screen` | true | false hides the band while a screen segment is on |
| heading | `shape` | `"skew"` | `"rounded"`: radius `rounded_radius_px` (20), upright text, #000 text, no animation |
| wipe | `position` | `"bottom-left"` | also bottom-right / top-left / top-right (centre mirrored) |
| wipe | `center_x_ratio` / `center_y_ratio` | 0.085 / 0.72 | circle centre for bottom-left. Legacy `margin_ratio` used only if these are absent |
| wipe | `diameter_ratio` / `small_ratio` | 0.22 / 0.16 | `size: "small"` picks `small_ratio` |
| wipe | `fade` | 0.2 | fade-in seconds at the start of each wipe segment |
| wipe | `border` | false | no rim (soft shadow only) |
| screen | `preset` | `"author"` | `author`: W*0.875 wide, top H*0.028, left W*0.092 (not centred), r 12px, bg #101627. `takkatw`: W*0.743, top 40px, centred, r 0. `custom`: `width_ratio`/`top_ratio`/`left_ratio`(omit=centred)/`radius_px` (legacy `radius_ratio` ok). A v1 settings without `preset` but with `width_ratio` is treated as `custom` |
| vertical_source | `background` | `"navy"` | `"blur"` = frosted copy of the source behind the 9:16 video |
| broll | `transition` / `duration` | `"dissolve"` / 0.33 | whole B-roll layout crossfades over the camera layout (10 f @ 30). Legacy `fade` used if `duration` absent |
| broll | `zoom_to` | 1.06 | slow zoom, **kind=photo only** (vertical is static) |
| broll | `vertical_center_x_ratio` / `vertical_center_y_ratio` / `vertical_max_h_ratio` / `vertical_radius_px` | 0.70 / 0.51 / 0.62 / 30 | vertical card geometry (speaker column W*0.40 on the left) |

### Style knobs that map to the "言葉で変えられる" items
| request | key |
|---|---|
| 丸ワイプを右下に | `wipe.position = "bottom-right"` (default is bottom-left) |
| 丸ワイプを小さめに | `wipe.size = "small"` (H*0.16) |
| 丸ワイプの顔位置 | `wipe.focus = {x, y}` (0-1, object-position) |
| 字幕の色 / 縁取り | `caption.color`, `caption.style = "outline"`, `caption.stroke_color` |
| 見出し帯を右上に | `heading.position = "top-right"` |
| 帯・文字の色 | `heading.band_color`, `heading.text_color` |
| 帯の形 | `heading.shape = "skew" \| "rounded"` |
| 画面収録を中央・小さめに（takkatw風） | `screen.preset = "takkatw"` |
| 縦素材の背景 | `vertical_source.background = "navy" \| "blur"` |

## v2 smoke test (this container)
`public/work` -> `runs/pretest/work` (cut.mp4 6 s 1280x720, used as both camera and "screen").
`public/work/timeline.json` = 8 s: 2 captions (0.3-2.5, 2.5-4.8), 1 heading (0.3-7.5), 1 screen segment (1.0-3.0),
1 vertical B-roll (3.5-5.5), 1 photo B-roll (5.8-7.8). Frames past the 6 s source hold the last frame.
`out/v2smoke.mp4`: 1920x1080 30 fps h264 yuv420p bt709 + aac, 8 s. Render ~3 min at concurrency 3 (software GL).
`out/v2smoke_NN.png` = 1 frame per second. `out/measure_v2.py <png>` prints the OpenCV measurements
(wipe circle fit, inset bbox, band edge angle, caption dark-ring stats). Results (frame 60, t=2 s):

| item | spec | measured |
|---|---|---|
| wipe centre / diameter | (163, 778) / 238 px | (161.9, 777.0) / 236.6 px (anti-aliased edge) |
| inset bbox | left 177, top 30, width 1680 (W*0.875) | left 177, top 30, width 1680, bottom 975 |
| takkatw preset | left 247, top 40, width 1427, centred | left 247, top 40, width 1426, centre 0.500W |
| band | top 59 (0.055H), left 86 (0.045W), height 90 (0.083H), skew -8.5deg | top 59, left 87, height 90, edges -8.49 / -8.52 deg |
| band rounded | edges vertical, text #000 | -0.16 / 0.08 deg, text median (0,0,0) |
| caption | glyph bottom 74 px above frame bottom (0.069H), size 0.048H | bottom margin 74 px, glyph height 49 px |
| caption shadow vs outline | shadow: dark only below/right; outline: dark ring all round | shadow: up 0.34 / down 0.57 / ring 0.50; outline: up 0.68 / down 0.66 / ring 0.70 |

## Known constraints
- Only `Background` plays audio. Every other `<OffthreadVideo>` (wipe, frosted glass, speaker column, screen) is `muted`.
  Do not add an unmuted copy or the audio doubles.
- `screen_cut.mp4` must be timeline-aligned with `cut.mp4` (cut_media.py cuts both with the same keep list). The inset uses
  `startFrom = segment.start`. There is no per-segment offset field.
- With the `author` inset preset the caption overlaps the bottom ~20 px of the inset (as in the reference videos); the
  inset is only shrunk when it would run off the bottom of the frame (portrait screen recordings).
- Frame extraction happens for every mounted video layer, so screen/broll segments render ~2-3x slower than plain talk.
  The base camera keeps rendering underneath the navy screen inset (needed for continuous audio; the overdraw is accepted).
- The font is loaded with the FontFace API and `delayRender`; if `public/fonts/NotoSansJP[wght].ttf` is missing the render
  fails with a clear error instead of silently falling back to a system font.
- Captions are `white-space: nowrap` and never wrap. Lines longer than ~26 full-width characters at 1080p will exceed 96 %
  of the width; keep captions.py at `max_chars` 18-20.
- `kind: "web"` samples the image's top-left pixel for the page colour unless `bg` is given (canvas needs same-origin,
  which staticFile satisfies).
- The circle wipe zooms the camera 1.35x around `wipe.focus` for 16:9 sources so the crop is head-and-shoulders; with 9:16
  sources it uses the frame as-is.
- In this container the full Playwright `chrome` binary refuses Remotion's old-headless launch
  ("Old Headless mode has been removed"); use `chromium_headless_shell` (works) or `--chrome-mode=chrome-for-testing`.
- No transitions between cuts (jump cuts) – by design. Only B-roll in/out dissolves.
- Output colour tags need `--color-space=bt709` (set in remotion.config.ts too); without it the file is flagged yuvj420p.
