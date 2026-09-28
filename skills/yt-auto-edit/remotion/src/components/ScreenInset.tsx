import React from 'react';
import {AbsoluteFill, OffthreadVideo, useVideoConfig} from 'remotion';
import {SCREEN_PRESETS, ScreenStyle, px} from '../types';

const parseAspect = (a?: string): number => {
  if (!a) return 16 / 9;
  const m = a.match(/^(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)$/);
  if (!m) return 16 / 9;
  return Number(m[1]) / Number(m[2]);
};

export type InsetBox = {left: number; top: number; width: number; height: number; radius: number};

/**
 * v2 A2 presets:
 *   author  (default) width W*0.875, top H*0.028, left W*0.092 (not centred), radius 12px, bg #101627
 *   takkatw           width W*0.743, top 40px, centred, radius 0
 *   custom            width_ratio / top_ratio / left_ratio (omit => centred) / radius_px (or legacy radius_ratio)
 * Legacy v1 settings (no `preset` but width_ratio etc.) are treated as "custom".
 */
export const insetBox = (style: ScreenStyle, width: number, height: number, screenAspect?: string): InsetBox => {
  const aspect = parseAspect(screenAspect);
  let preset = style.preset;
  if (!preset && (style.width_ratio != null || style.top_ratio != null)) preset = 'custom';
  if (!preset) preset = 'author';
  const p =
    preset === 'custom'
      ? {
          width_ratio: style.width_ratio ?? SCREEN_PRESETS.author.width_ratio,
          top_ratio: style.top_ratio ?? SCREEN_PRESETS.author.top_ratio,
          left_ratio: style.left_ratio,
          radius_px:
            style.radius_px ?? (style.radius_ratio != null ? (style.radius_ratio * 1080) : SCREEN_PRESETS.author.radius_px),
        }
      : SCREEN_PRESETS[preset];
  const top = height * p.top_ratio;
  let boxW = width * p.width_ratio;
  let boxH = boxW / aspect;
  // never run off the bottom of the frame (portrait screen recordings etc.)
  const maxH = height - top - px(20, height);
  if (boxH > maxH) {
    boxH = maxH;
    boxW = boxH * aspect;
  }
  // v3: 字幕帯と重ならないよう、下端が max_bottom_ratio(既定 0.83H) を超える場合は縮小（アスペクト・上余白・左余白は維持）
  const maxBottom = height * ((p as any).max_bottom_ratio ?? (style as any).max_bottom_ratio ?? 0.83);
  if (top + boxH > maxBottom) {
    boxH = Math.max(1, maxBottom - top);
    boxW = boxH * aspect;
  }
  const left = p.left_ratio != null ? width * p.left_ratio : (width - boxW) / 2;
  return {left, top, width: boxW, height: boxH, radius: px(p.radius_px, height)};
};

/**
 * Navy background with the screen recording inset (see insetBox). The caption sits over the
 * bottom edge of the inset in the author's videos, so no caption zone is reserved.
 * `startFrom` = timeline frame where this segment starts (screen_cut.mp4 is timeline-aligned).
 */
export const ScreenInset: React.FC<{
  src: string;
  startFrom: number;
  style: ScreenStyle;
  screenAspect?: string;
}> = ({src, startFrom, style, screenAspect}) => {
  const {width, height} = useVideoConfig();
  const box = insetBox(style, width, height, screenAspect);
  const full = style.layout === 'full';
  return (
    <AbsoluteFill style={{background: style.bg}}>
      <div
        style={{
          position: 'absolute',
          top: full ? 0 : box.top,
          left: full ? 0 : box.left,
          width: full ? width : box.width,
          height: full ? height : box.height,
          borderRadius: full ? 0 : box.radius,
          overflow: 'hidden',
          background: '#000',
          boxShadow: full ? undefined : '0 8px 30px rgba(0,0,0,0.45)',
        }}
      >
        <OffthreadVideo
          src={src}
          muted
          startFrom={startFrom}
          style={{width: '100%', height: '100%', objectFit: full ? 'cover' : 'contain'}}
        />
      </div>
    </AbsoluteFill>
  );
};
