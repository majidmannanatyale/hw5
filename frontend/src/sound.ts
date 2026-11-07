// Tiny chiptune synth (Web Audio). No audio files. Respects the mute toggle.
let ctx: AudioContext | null = null;
const KEY = "cc-deck-muted";

export const isMuted = () => localStorage.getItem(KEY) === "1";
export const setMuted = (m: boolean) => localStorage.setItem(KEY, m ? "1" : "0");

/** Browsers only allow audio after a click; call this from any click handler. */
export function unlockAudio() {
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
}

function tone(freq: number, start: number, dur: number, type: OscillatorType = "square", vol = 0.06) {
  if (!ctx) return;
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = type; o.frequency.value = freq;
  g.gain.setValueAtTime(0, start);
  g.gain.linearRampToValueAtTime(vol, start + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  o.connect(g).connect(ctx.destination);
  o.start(start); o.stop(start + dur + 0.02);
}

function pop(start: number) {
  if (!ctx) return;
  const len = Math.floor(ctx.sampleRate * 0.25);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
  const src = ctx.createBufferSource(), g = ctx.createGain(), f = ctx.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = 1800;
  g.gain.value = 0.08;
  src.buffer = buf; src.connect(f).connect(g).connect(ctx.destination); src.start(start);
}

/** "Quest clear" fanfare plus firework pops. */
export function playFanfare() {
  if (isMuted() || !ctx) return;
  const t = ctx.currentTime + 0.05;
  [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(f, t + i * 0.09, 0.16));
  tone(783.99, t + 0.42, 0.12); tone(1046.5, t + 0.56, 0.45, "square", 0.07);
  tone(261.63, t, 0.7, "triangle", 0.05);
  [0.9, 1.25, 1.6, 2.1].forEach(d => pop(t + d));
}

/** Soft blip when an agent finishes its part. */
export function playBlip() {
  if (isMuted() || !ctx) return;
  const t = ctx.currentTime + 0.01;
  tone(880, t, 0.08, "triangle", 0.04); tone(1318.5, t + 0.06, 0.1, "triangle", 0.035);
}
