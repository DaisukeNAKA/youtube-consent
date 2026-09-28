import React from 'react';
import {AbsoluteFill, OffthreadVideo, useVideoConfig} from 'remotion';
import {NAVY, VerticalSourceStyle} from '../types';

export {NAVY};

/**
 * Base camera layer.
 * 16:9 source: plays full-frame.
 * 9:16 source: full-height, centred, over flat navy #101627 (v2 A7 default) or a blurred+dimmed
 *              enlarged copy (vertical_source.background = "blur").
 * This is the ONLY unmuted video element; every other copy of the camera is muted.
 */
export const Background: React.FC<{
  src: string;
  sourceAspect: '16:9' | '9:16';
  style: VerticalSourceStyle;
}> = ({src, sourceAspect, style}) => {
  const {width, height} = useVideoConfig();
  if (sourceAspect !== '9:16') {
    return (
      <AbsoluteFill style={{background: '#000'}}>
        <OffthreadVideo src={src} style={{width, height, objectFit: 'cover'}} />
      </AbsoluteFill>
    );
  }
  const blur = style.background === 'blur';
  return (
    <AbsoluteFill style={{background: NAVY}}>
      {blur ? (
        <AbsoluteFill style={{overflow: 'hidden'}}>
          <OffthreadVideo
            src={src}
            muted
            style={{
              width,
              height,
              objectFit: 'cover',
              transform: 'scale(1.15)',
              filter: `blur(${style.blur_px}px)`,
            }}
          />
          <AbsoluteFill style={{background: `rgba(0,0,0,${style.dim})`}} />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <OffthreadVideo
          src={src}
          style={{height, width: 'auto', objectFit: 'contain', boxShadow: '0 0 40px rgba(0,0,0,0.35)'}}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
