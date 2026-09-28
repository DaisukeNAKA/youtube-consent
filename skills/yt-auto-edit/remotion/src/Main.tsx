import React, {useEffect} from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {ensureFont} from './font';
import {resolveMedia, sec2frame} from './media';
import {Timeline, resolveStyle} from './types';
import {Background} from './components/Background';
import {Caption} from './components/Caption';
import {HeadingBand} from './components/HeadingBand';
import {ScreenInset} from './components/ScreenInset';
import {CircleWipe} from './components/CircleWipe';
import {BrollCard} from './components/BrollCard';

/**
 * Layer order (bottom -> top):
 *   Background(camera, audio) -> [screenSegments: ScreenInset + CircleWipe] -> [broll cards, dissolved]
 *   -> HeadingBand -> Caption
 * v2: the heading band stays up during screen segments unless heading.show_during_screen is false.
 */
export const Main: React.FC<Timeline> = (props) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const style = resolveStyle(props.style);
  const cam = resolveMedia(props.video);
  const screen = props.screen ? resolveMedia(props.screen) : null;
  const t = frame / fps;
  const inScreen = Boolean(screen) && (props.screenSegments ?? []).some((s) => t >= s.start && t < s.end);
  const hideHeading = inScreen && style.heading.show_during_screen === false;

  useEffect(() => {
    ensureFont();
  }, []);

  return (
    <AbsoluteFill style={{background: '#000'}}>
      <Background src={cam} sourceAspect={props.sourceAspect} style={style.vertical_source} />

      {screen
        ? (props.screenSegments ?? []).map((seg, i) => {
            const from = sec2frame(seg.start, fps);
            const dur = Math.max(1, sec2frame(seg.end, fps) - from);
            return (
              <Sequence key={`screen-${i}`} from={from} durationInFrames={dur} name={`screen ${i}`}>
                <ScreenInset src={screen} startFrom={from} style={style.screen} screenAspect={props.screenAspect} />
                <CircleWipe src={cam} startFrom={from} style={style.wipe} sourceAspect={props.sourceAspect} />
              </Sequence>
            );
          })
        : null}

      {(props.broll ?? []).map((cue, i) => {
        const from = sec2frame(cue.start, fps);
        const dur = Math.max(1, sec2frame(cue.end, fps) - from);
        return (
          <Sequence key={`broll-${i}`} from={from} durationInFrames={dur} name={`broll ${i}`}>
            <BrollCard
              cue={cue}
              img={resolveMedia(cue.file)}
              cam={cam}
              startFrom={from}
              style={style.broll}
              wipe={style.wipe}
            />
          </Sequence>
        );
      })}

      <HeadingBand cues={props.headings ?? []} style={style.heading} hidden={hideHeading} />
      <Caption cues={props.captions ?? []} style={style.caption} />
    </AbsoluteFill>
  );
};
