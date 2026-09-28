import {cancelRender, continueRender, delayRender, staticFile} from 'remotion';

export const FONT_FAMILY = 'Noto Sans JP';
let loaded: Promise<void> | null = null;

/**
 * Load public/fonts/NotoSansJP[wght].ttf (variable, wght 100-900) via the FontFace API
 * and block rendering until it is ready. Idempotent across components.
 */
export const ensureFont = (): Promise<void> => {
  if (loaded) return loaded;
  if (typeof document === 'undefined' || typeof FontFace === 'undefined') {
    loaded = Promise.resolve();
    return loaded;
  }
  const handle = delayRender('Loading Noto Sans JP', {timeoutInMilliseconds: 60000});
  const url = staticFile('fonts/NotoSansJP[wght].ttf');
  const face = new FontFace(FONT_FAMILY, `url("${url}") format("truetype")`, {
    weight: '100 900',
    style: 'normal',
    display: 'block',
  });
  loaded = face
    .load()
    .then((f) => {
      document.fonts.add(f);
      return document.fonts.load(`900 40px "${FONT_FAMILY}"`).then(() => undefined);
    })
    .then(() => continueRender(handle))
    .catch((err) => {
      cancelRender(err);
    });
  return loaded;
};
