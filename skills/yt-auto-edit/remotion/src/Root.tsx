import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Main';
import {DEFAULT_STYLE, Timeline} from './types';

const defaultProps: Timeline = {
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 240,
  video: 'cut.mp4',
  screen: null,
  sourceAspect: '16:9',
  style: DEFAULT_STYLE,
  captions: [],
  headings: [],
  screenSegments: [],
  broll: [],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Main"
      component={Main}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={240}
      defaultProps={defaultProps}
      calculateMetadata={async ({props}) => {
        const fps = props.fps || 30;
        let durationInFrames = props.durationInFrames;
        if (!durationInFrames || durationInFrames <= 0) {
          // fall back to the length of the cut video
          const {getVideoMetadata} = await import('@remotion/media-utils');
          const {resolveMedia} = await import('./media');
          const meta = await getVideoMetadata(resolveMedia(props.video));
          durationInFrames = Math.max(1, Math.round(meta.durationInSeconds * fps));
        }
        return {
          width: props.width || 1920,
          height: props.height || 1080,
          fps,
          durationInFrames,
          props: {...props, fps, durationInFrames},
        };
      }}
    />
  );
};
