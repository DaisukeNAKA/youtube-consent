import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT_FAMILY} from '../font';
import {CaptionCue, CaptionStyle, px} from '../types';

/**
 * White one-line caption, bottom-centre, never wraps.
 * v2 A4
 *   style "shadow"  (default): no outline; drop shadow offset 2px, blur 5px, rgba(0,0,0,.5)
 *   style "outline"          : black stroke H*0.004 painted OUTSIDE the glyphs + the same shadow
 * Size H*0.048, glyph box bottom at H*0.069 from the frame bottom.
 * A legacy v1 style (no `style` key) falls back to "shadow" too (v2 default).
 */
export const Caption: React.FC<{cues: CaptionCue[]; style: CaptionStyle}> = ({cues, style}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const cue = cues.find((c) => t >= c.start && t < c.end);
  if (!cue) return null;

  const outline = style.style === 'outline';
  const fontSize = height * style.size_ratio;
  const strokePx = height * style.stroke_ratio;
  const bottom = height * style.bottom_ratio;
  const family = `"${style.font || FONT_FAMILY}", "${FONT_FAMILY}", "Noto Sans CJK JP", sans-serif`;
  const shOff = px(style.shadow_offset_px ?? 2, height);
  const shBlur = px(style.shadow_blur_px ?? 5, height);
  const shadow = `${shOff}px ${shOff}px ${shBlur}px rgba(0,0,0,${style.shadow_alpha ?? 0.5})`;

  const text: React.CSSProperties = {
    fontFamily: family,
    fontWeight: style.weight,
    fontSize,
    lineHeight: 1.25,
    color: style.color,
    whiteSpace: 'nowrap',
    letterSpacing: '0.01em',
    textAlign: 'center',
    maxWidth: width * 0.96,
    overflow: 'visible',
    textShadow: outline && !style.shadow ? undefined : shadow,
  };
  if (outline) {
    // stroke is centred on the outline -> use 2x width and paint it under the fill
    text.WebkitTextStroke = `${strokePx * 2}px ${style.stroke_color}`;
    text.paintOrder = 'stroke fill';
  }
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', pointerEvents: 'none'}}>
      <div style={{...text, marginBottom: bottom - fontSize * 0.12}}>{cue.text}</div>
    </AbsoluteFill>
  );
};
