import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  cancelRender,
  continueRender,
  delayRender,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {BrollCue, BrollStyle, WipeStyle, px} from '../types';

/** Frosted glass: blurred, enlarged camera + white overlay */
const Frosted: React.FC<{cam: string; startFrom: number; style: BrollStyle; box: React.CSSProperties}> = ({
  cam,
  startFrom,
  style,
  box,
}) => (
  <div style={{position: 'absolute', overflow: 'hidden', ...box}}>
    <OffthreadVideo
      src={cam}
      muted
      startFrom={startFrom}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        transform: 'scale(1.2)',
        filter: `blur(${style.blur_px}px) saturate(1.2)`,
      }}
    />
    <div style={{position: 'absolute', inset: 0, background: `rgba(255,255,255,${style.glass_white})`}} />
  </div>
);

const useTopLeftColor = (src: string, enabled: boolean, fallback?: string): string | undefined => {
  const [color, setColor] = useState<string | undefined>(fallback);
  useEffect(() => {
    if (!enabled || fallback) return;
    const handle = delayRender('sampling web bg color');
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      try {
        const c = document.createElement('canvas');
        c.width = 2;
        c.height = 2;
        const ctx = c.getContext('2d');
        if (!ctx) throw new Error('no 2d ctx');
        ctx.drawImage(img, 0, 0, 2, 2, 0, 0, 2, 2);
        const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
        setColor(`rgb(${r},${g},${b})`);
      } catch (e) {
        setColor('#FFFFFF');
      }
      continueRender(handle);
    };
    img.onerror = (e) => cancelRender(new Error(`broll image failed: ${src} ${String(e)}`));
    img.src = src;
  }, [src, enabled, fallback]);
  return color;
};

/** seconds of the layout dissolve (v2 A6: 0.33 s = 10 f @ 30). Legacy `fade` is honoured when `duration` is absent. */
export const brollTransitionSec = (style: BrollStyle): number => {
  if (style.transition === 'none') return 0;
  return style.duration ?? style.fade ?? 0.33;
};

/**
 * v5 B-roll (v2 A5/A6).
 * vertical: camera (face-centred, full height) in the left W*0.40, frosted glass on the right with a
 *           STATIC rounded card (radius 30px, shadow) centred at (0.70W, 0.51H), max height 0.62H.
 * photo:    full-screen frosted glass + centred rounded card (radius H*0.028), slow zoom 1.00 -> zoom_to.
 * web:      full-screen on the page's background colour (cue.bg or sampled from the image).
 * The whole B-roll layout is dissolved in/out over `duration` seconds on top of the camera layout
 * (both layouts are rendered; this layer's opacity crossfades between them).
 */
export const BrollCard: React.FC<{
  cue: BrollCue;
  img: string;
  cam: string;
  startFrom: number;
  style: BrollStyle;
  wipe: WipeStyle;
}> = ({cue, img, cam, startFrom, style, wipe}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const durF = Math.max(1, Math.round((cue.end - cue.start) * fps));
  const trSec = brollTransitionSec(style);
  const trF = Math.round(trSec * fps);
  const opacity =
    trF > 0
      ? interpolate(frame, [0, trF, Math.max(trF, durF - trF), Math.max(trF + 1, durF)], [0, 1, 1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
      : 1;
  const zoom = interpolate(frame, [0, durF], [1, style.zoom_to], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const webBg = useTopLeftColor(img, cue.kind === 'web', cue.bg);

  const card = (maxW: number, maxH: number, radius: number, scale: number): React.ReactNode => (
    <div
      style={{
        borderRadius: radius,
        overflow: 'hidden',
        boxShadow: '0 18px 50px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.2)',
        transform: `scale(${scale})`,
        transformOrigin: 'center center',
        background: '#fff',
        lineHeight: 0,
      }}
    >
      <Img src={img} style={{maxWidth: maxW, maxHeight: maxH, width: 'auto', height: 'auto', display: 'block'}} />
    </div>
  );

  if (cue.kind === 'vertical') {
    const camW = width * style.speaker_width_ratio;
    const fx = Math.round(wipe.focus.x * 100);
    const fy = Math.round(wipe.focus.y * 100);
    const cx = width * (style.vertical_center_x_ratio ?? 0.7);
    const cy = height * (style.vertical_center_y_ratio ?? 0.51);
    const maxH = height * (style.vertical_max_h_ratio ?? 0.62);
    const maxW = (width - camW) * 0.9;
    return (
      <AbsoluteFill style={{opacity}}>
        <Frosted cam={cam} startFrom={startFrom} style={style} box={{left: camW, top: 0, width: width - camW, height}} />
        <div style={{position: 'absolute', left: 0, top: 0, width: camW, height, overflow: 'hidden', background: '#000'}}>
          <OffthreadVideo
            src={cam}
            muted
            startFrom={startFrom}
            style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: `${fx}% ${fy}%`}}
          />
        </div>
        {/* card centred on (cx, cy); static (no zoom) */}
        <div
          style={{
            position: 'absolute',
            left: cx - maxW / 2,
            top: cy - maxH / 2,
            width: maxW,
            height: maxH,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {card(maxW, maxH, px(style.vertical_radius_px ?? 30, height), 1)}
        </div>
      </AbsoluteFill>
    );
  }

  if (cue.kind === 'photo') {
    return (
      <AbsoluteFill style={{opacity}}>
        <Frosted cam={cam} startFrom={startFrom} style={style} box={{left: 0, top: 0, width, height}} />
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
          {card(width * 0.86, height * 0.84, height * style.card_radius_ratio, zoom)}
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  // web
  return (
    <AbsoluteFill style={{opacity, background: webBg ?? '#FFFFFF', alignItems: 'center', justifyContent: 'center'}}>
      <Img src={img} style={{width, height, objectFit: 'contain'}} />
    </AbsoluteFill>
  );
};
