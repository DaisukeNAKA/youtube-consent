import {Config} from '@remotion/cli/config';
// SPEC.md 2.7: H.264 (libx264, crf 18, yuv420p), AAC 192k
Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
Config.setCodec('h264');
Config.setCrf(18);
Config.setPixelFormat('yuv420p');
Config.setColorSpace('bt709'); // -> yuv420p / tv range / bt709 tags (without it: yuvj420p pc range)
Config.setAudioCodec('aac');
Config.setAudioBitrate('192k');
