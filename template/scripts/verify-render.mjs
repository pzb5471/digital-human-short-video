import {execFileSync, spawnSync} from 'node:child_process';

const video = new URL('../out/test.mp4', import.meta.url);
const path = decodeURIComponent(video.pathname).replace(/^\/([A-Za-z]:)/, '$1');
const pixel = execFileSync(
  'ffmpeg',
  [
    '-v',
    'error',
    '-ss',
    '3.5',
    '-i',
    path,
    '-vf',
    'crop=1:1:540:960,format=rgb24',
    '-frames:v',
    '1',
    '-f',
    'rawvideo',
    'pipe:1',
  ],
  {stdio: ['ignore', 'pipe', 'pipe']},
);
if (
  pixel.length < 3 ||
  [pixel[0], pixel[1], pixel[2]].some((value) => Math.abs(value - 32) > 10)
) {
  throw new Error(`paid primary pixel missing: ${[...pixel.slice(0, 3)]}`);
}

const silence = spawnSync(
  'ffmpeg',
  [
    '-hide_banner',
    '-i',
    path,
    '-af',
    'silencedetect=noise=-35dB:d=0.75',
    '-f',
    'null',
    '-',
  ],
  {encoding: 'utf8'},
);
if (silence.status !== 0) {
  throw new Error(`audio verification failed: ${silence.stderr}`);
}
const silenceDurations = [...silence.stderr.matchAll(/silence_duration:\s*([0-9.]+)/g)].map(
  (match) => Number(match[1]),
);
if (silenceDurations.some((duration) => duration >= 0.75)) {
  throw new Error(`rendered fixture contains excessive silence: ${silence.stderr}`);
}

console.log('Verified paid primary pixel and audible primary audio');
