import { useEffect, useRef } from "react";

const COLORS = ["#5b8cff", "#9cc2ff", "#46e39b", "#ffd166", "#b28dff", "#4fd1c5", "#ff7eb6", "#eef3ff"];
type P = { x: number; y: number; vx: number; vy: number; life: number; c: string };

/** Pixel fireworks over the whole screen for ~3.5s, with a "QUEST CLEAR" banner. */
export function Fireworks({ label, onDone }: { label: string; onDone: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const end = setTimeout(onDone, reduced ? 2600 : 3800);
    if (reduced) return () => clearTimeout(end);
    const cv = ref.current!, g = cv.getContext("2d")!;
    const W = (cv.width = window.innerWidth), H = (cv.height = window.innerHeight);
    const parts: P[] = [];
    const burst = (x: number, y: number) => {
      const c = COLORS[Math.floor(Math.random() * COLORS.length)];
      for (let i = 0; i < 46; i++) {
        const a = (i / 46) * Math.PI * 2, s = 1.6 + Math.random() * 2.6;
        parts.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, c: Math.random() < .2 ? "#eef3ff" : c });
      }
    };
    const timers = [0, 380, 760, 1150, 1600, 2050].map((d, i) =>
      setTimeout(() => burst(W * (0.2 + ((i * 0.37) % 0.6)), H * (0.18 + ((i * 0.23) % 0.3))), d));
    let raf = 0;
    const tick = () => {
      g.clearRect(0, 0, W, H);
      for (const p of parts) {
        p.x += p.vx; p.y += p.vy; p.vy += 0.035; p.vx *= 0.985; p.life -= 0.012;
        if (p.life <= 0) continue;
        g.globalAlpha = Math.max(0, p.life);
        g.fillStyle = p.c;
        g.fillRect(Math.round(p.x / 4) * 4, Math.round(p.y / 4) * 4, 4, 4);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); timers.forEach(clearTimeout); clearTimeout(end); };
  }, [onDone, reduced]);

  return (
    <div className="fireworks" role="status" aria-live="assertive">
      {!reduced && <canvas ref={ref} />}
      <div className="quest-clear"><span>QUEST CLEAR</span><small>{label}</small></div>
    </div>
  );
}
