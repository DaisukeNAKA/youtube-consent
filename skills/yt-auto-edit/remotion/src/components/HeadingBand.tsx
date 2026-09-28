import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT_FAMILY} from '../font';
import {HeadingCue, HeadingStyle, px} from '../types';

/** band height = fontSize * LINE_HEIGHT + 2 * padY  (=> ~H*0.083 with size 0.041H and pad 20px) */
const LINE_HEIGHT = 1.12;

/**
 * Top-left white band with dark text.
 * v2 A3
 *   shape=skew   : the whole band container is skewX(skew_deg) (default -8.5deg) so the text leans with it
 *                  (pseudo italic). In = slide from the band's side over anim_in (0.25 s); out = instant.
 *   shape=rounded: rounded rectangle (20px), upright text, colour #000, no animation.
 * Visibility during screen segments is decided by Main (heading.show_during_screen).
 */
export const HeadingBand: React.FC<{cues: HeadingCue[]; style: HeadingStyle; hidden?: boolean}> = ({
  cues,
  style,
  hidden,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const cue = cues.find((c) => t >= c.start && t < c.end);
  if (!cue || hidden) return null;

  const rounded = style.shape === 'rounded';
  const fontSize = height * style.size_ratio;
  const padX = style.pad_x_px != null ? px(style.pad_x_px, height) : width * (style.pad_x_ratio ?? 0.019);
  const padY = style.pad_y_px != null ? px(style.pad_y_px, height) : height * (style.pad_y_ratio ?? 0.02);
  const mx = width * style.margin_x_ratio;
  const my = height * style.margin_y_ratio;
  const skew = rounded ? 0 : style.skew_deg;
  const bandH = fontSize * LINE_HEIGHT + padY * 2;
  // the skewed band's outer corner pokes out by tan(skew)*bandH/2; compensate so the
  // leftmost (or rightmost) point sits on the margin
  const skewComp = Math.abs(Math.tan((skew * Math.PI) / 180)) * (bandH / 2);
  const isRight = style.position === 'top-right';

  const animIn = style.anim_in ?? 0.25;
  const anim = rounded ? 'none' : style.anim;
  const p =
    anim === 'none'
      ? 1
      : interpolate(t - cue.start, [0, animIn], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const eased = 1 - Math.pow(1 - p, 3);
  const slide = anim === 'slide' ? (1 - eased) * (isRight ? 1 : -1) * width * 0.04 : 0;
  const opacity = anim === 'none' ? 1 : eased;

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          top: my,
          ...(isRight ? {right: mx} : {left: mx}),
          transform: `translateX(${slide}px)`,
          opacity,
        }}
      >
        <div
          style={{
            marginLeft: isRight ? 0 : skewComp,
            marginRight: isRight ? skewComp : 0,
            background: style.band_color,
            transform: skew ? `skewX(${skew}deg)` : undefined,
            borderRadius: rounded ? px(style.rounded_radius_px ?? 20, height) : 0,
            padding: `${padY}px ${padX}px`,
            boxShadow: '0 4px 14px rgba(0,0,0,0.25)',
            display: 'inline-block',
            fontFamily: `"${FONT_FAMILY}", "Noto Sans CJK JP", sans-serif`,
            fontWeight: 800,
            fontSize,
            lineHeight: LINE_HEIGHT,
            // rounded => #000 unless the user explicitly changed the text colour
            color: rounded && style.text_color.toUpperCase() === '#182028' ? '#000000' : style.text_color,
            whiteSpace: 'nowrap',
            letterSpacing: '0.02em',
          }}
        >
          {cue.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
