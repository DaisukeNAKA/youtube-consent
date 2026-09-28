import React from 'react';
import {AbsoluteFill, OffthreadVideo, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {WipeStyle} from '../types';

/**
 * Circular crop of the camera (face-centred via focus), fixed near a corner.
 * v2 A1: default bottom-left, centre (W*0.085, H*0.72), diameter H*0.22 (small: H*0.16), no border,
 * 0.2 s fade-in at the start of the segment (frame 0 of the enclosing <Sequence>).
 * The centre ratios are given for bottom-left and mirrored for the other three positions.
 * Legacy settings (v1) with `margin_ratio` and no centre ratios are honoured as before.
 */
export const wipeGeometry = (
  style: WipeStyle,
  width: number,
  height: number,
): {cx: number; cy: number; d: number} => {
  const d = height * (style.size === 'small' ? style.small_ratio : style.diameter_ratio);
  const right = style.position.endsWith('right');
  const top = style.position.startsWith('top');
  let cx: number;
  let cy: number;
  if (style.center_x_ratio != null && style.center_y_ratio != null) {
    cx = width * style.center_x_ratio;
    cy = height * style.center_y_ratio;
  } else {
    const m = height * (style.margin_ratio ?? 0.04);
    cx = m + d / 2;
    cy = height - m - d / 2;
  }
  if (right) cx = width - cx;
  if (top) cy = height - cy;
  return {cx, cy, d};
};

export const CircleWipe: React.FC<{
  src: string;
  startFrom: number;
  style: WipeStyle;
  sourceAspect: '16:9' | '9:16';
}> = ({src, startFrom, style, sourceAspect}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {cx, cy, d} = wipeGeometry(style, width, height);
  const fadeF = Math.max(1, Math.round((style.fade ?? 0) * fps));
  const opacity =
    style.fade && style.fade > 0
      ? interpolate(frame, [0, fadeF], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
      : 1;
  const fx = Math.round(style.focus.x * 100);
  const fy = Math.round(style.focus.y * 100);
  // zoom in a little so the crop is head-and-shoulders, not the whole frame
  const zoom = sourceAspect === '9:16' ? 1.0 : 1.35;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: cx - d / 2,
          top: cy - d / 2,
          width: d,
          height: d,
          borderRadius: '50%',
          overflow: 'hidden',
          opacity,
          boxShadow: '0 6px 18px rgba(0,0,0,0.35)',
          border: style.border ? `${Math.max(2, height * 0.004)}px solid #FFFFFF` : undefined,
          boxSizing: 'border-box',
          background: '#000',
        }}
      >
        <OffthreadVideo
          src={src}
          muted
          startFrom={startFrom}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: `${fx}% ${fy}%`,
            transform: `scale(${zoom})`,
            transformOrigin: `${fx}% ${fy}%`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
