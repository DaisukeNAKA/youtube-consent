import {staticFile} from 'remotion';

/** Resolve a timeline path: absolute URLs pass through, everything else is under public/work/. */
export const resolveMedia = (p: string): string => {
  if (/^(https?:|data:|blob:)/.test(p)) return p;
  if (p.startsWith('/')) {
    // absolute local path -> not servable by the bundle; assume caller linked it under public/work
    const base = p.split('/').pop() as string;
    return staticFile(`work/${base}`);
  }
  return staticFile(`work/${p}`);
};

export const sec2frame = (s: number, fps: number): number => Math.round(s * fps);
