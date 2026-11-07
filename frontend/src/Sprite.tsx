import type { ReactElement } from "react";
import type { AgentId } from "./api";
import { AGENTS } from "./agents";

// Original 16x16 pixel sprites. "." is transparent; P/p are the agent's own color and shade.
const GRIDS: Record<AgentId, string[]> = {
  // King Grimhorn: an original horned beast-king with a crown, heavy brow, glowing eyes and little fangs.
  boss: [
    "H....C.CC.C....H",
    "HH...CCCCCC...HH",
    ".HH.KccccccK.HH.",
    "..HKPPPPPPPPKH..",
    "...KBBPPPPBBK...",
    "..KPEEBPPBEEPK..",
    "..KPPEPPPPEPPK..",
    "..KPPPPppPPPPK..",
    "..KPLLLLLLLLPK..",
    "..KPLWKKKKWLPK..",
    "...KPLLLLLLPK...",
    "..KpKPPPPPPKpK..",
    ".KpppKLLLLKpppK.",
    ".KpppPLLLLPpppK.",
    ".KccKPPPPPPKccK.",
    "..KKK.KKKK.KKK..",
  ],
  // Pip Stockwell: cap and clipboard.
  inventory: [
    "................",
    ".....KKKKKK.....",
    "....KPPPPPPK....",
    "...KPPPPPPPPPPK.",
    "....KhhhhhhK....",
    "....KSESSESK....",
    "....KSSSSSSK....",
    "....KSSMMSSK....",
    ".....KSSSSK.....",
    "....KPPPPPPK....",
    "...KPPPPPPPPK...",
    "..KSKPPPPPPKWWK.",
    "..KSKPPPPPPKWAK.",
    "....KppppppKWWK.",
    "....KpK..KpK....",
    "....KKK..KKK....",
  ],
  // Ada Ledger: bun and round glasses.
  accounting: [
    "......KKKK......",
    ".....KHHHHK.....",
    "....KHHHHHHK....",
    "...KHHHHHHHHK...",
    "...KHSSSSSSHK...",
    "...KHGGSSGGHK...",
    "...KSGESSEGSK...",
    "....KSSSSSSK....",
    "....KSSMMSSK....",
    ".....KSSSSK.....",
    "....KPPWWPPK....",
    "...KPPPWWPPPK...",
    "..KSKPPPPPPKSK..",
    "....KppppppK....",
    "....KpK..KpK....",
    "....KKK..KKK....",
  ],
  // Bo Brickley: hard hat, overalls, wrench.
  facilities: [
    "................",
    ".....KKKKKK.....",
    "....KPPPPPPK....",
    "..KKPPPPPPPPKK..",
    "..KppppppppppK..",
    "....KSESSESK....",
    "....KSSSSSSK....",
    "....KSsMMsSK....",
    ".....KssssK.....",
    "....KWPWWPWK....",
    "...KWWPWWPWWK...",
    "..KSKPPPPPPKSKGK",
    "..KSKPPPPPPKSGK.",
    "....KppppppKGK..",
    "....KpK..KpK....",
    "....KKK..KKK....",
  ],
  // Sunny Vale: headset with a mic and rosy cheeks.
  customer_service: [
    "................",
    ".....KKKKKK.....",
    "....KHHHHHHK....",
    "...KHHHHHHHHK...",
    "..GKHSSSSSSHKG..",
    "..GKSSESSESSKG..",
    "..GKSRSSSSRSKG..",
    "...KGSSMMSSSK...",
    "....KGGSSSK.....",
    "....KPPPPPPK....",
    "...KPPPWWPPPK...",
    "..KSKPPPPPPKSK..",
    "..KSKPPPPPPKSK..",
    "....KppppppK....",
    "....KpK..KpK....",
    "....KKK..KKK....",
  ],
};

const BASE: Record<string, string> = {
  K: "#0d1222", S: "#f1c9a5", s: "#d29f7c", E: "#0d1222", M: "#b85c5c", W: "#eef3ff", A: "#8a97b3",
  G: "#9aa6c4", R: "#f39aa8", h: "#5a3b2a", L: "#d9cbff",
};
const PER_AGENT: Partial<Record<AgentId, Record<string, string>>> = {
  boss: { H: "#efe3c4", C: "#ffd166", c: "#d9a227", B: "#3a2a70", E: "#ff5f6d", W: "#ffffff", K: "#140f26" },
  accounting: { H: "#3b2a22", G: "#c9d6f2" },
  customer_service: { H: "#e8b86b" },
};

export function Sprite({ agent, size = 64, title, className }:
  { agent: AgentId; size?: number; title?: string; className?: string }) {
  const meta = AGENTS[agent];
  const colors: Record<string, string> = { ...BASE, P: meta.color, p: meta.dark, ...(PER_AGENT[agent] ?? {}) };
  const rects: ReactElement[] = [];
  GRIDS[agent].forEach((row, y) => [...row].forEach((ch, x) => {
    if (ch !== "." && colors[ch]) rects.push(<rect key={`${x}-${y}`} x={x} y={y} width={1.02} height={1.02} fill={colors[ch]} />);
  }));
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} shapeRendering="crispEdges"
         role="img" aria-label={title ?? meta.name} className={className}>
      {rects}
    </svg>
  );
}
