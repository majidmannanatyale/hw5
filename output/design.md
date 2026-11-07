# Campus Customs Command Deck: Design Reference

This is the reference for how the dashboard looks, sounds, and behaves. The dashboard lives in `hw5/frontend`. It is built with React, Vite and TypeScript, runs with `npm run dev`, and talks to the FastAPI backend at `http://localhost:8000`.

---

## 1. Feel

* **80s retro bit-interface, but sleek and elegant.** Think of a calm arcade cabinet at night: pixel type for headings and badges, crisp modern type for reading, and soft glows rather than neon. Nothing punchy, no flashing, no loud gradients.
* **Like a game.** Tickets are *quests*, agents are a *party* of characters, a run is a *mission*, and approvals are *decisions only the player (Majid) can make*. Closing a ticket is a level-clear moment, with fireworks and a short chiptune.
* **Calm by default.** Motion is slow and purposeful. Everything respects `prefers-reduced-motion`, and sound has a mute toggle that is remembered.

## 2. Color

Mostly blue and grey, with a few accents.

| Role | Color | Use |
|---|---|---|
| Night (background) | `#0b1020` | Page background |
| Deep panel | `#121a2e` | Cards and panels |
| Raised panel | `#1a2440` | Hover, nested panels |
| Grid line | `#26324f` | Borders and pixel grid |
| Steel (text) | `#d8e1f0` | Main text |
| Fog (muted) | `#8a97b3` | Secondary text |
| Arcade blue (primary) | `#5b8cff` | Buttons, focus, selected tab |
| Ice (highlight) | `#9cc2ff` | Links, soft glows |

**Progress lamps** (round indicators):

| State | Color | Meaning |
|---|---|---|
| Red | `#ff5f6d` | Not started |
| Yellow | `#ffd166` | In progress (gentle pulse) |
| Green | `#46e39b` | Done. **Stays green.** |

**Agent colors** are always used for that agent's sprite, name, speech bubbles, summaries, and leaderboard row:

| Agent | Color |
|---|---|
| Boss | Royal violet `#b28dff` |
| Inventory | Teal `#4fd1c5` |
| Accounting | Periwinkle `#7aa2ff` |
| Facilities | Copper `#ff9f5a` |
| Customer service | Rose `#ff7eb6` |

## 3. Type

* **Pixel headings and badges:** *Pixelify Sans* (bundled with `@fontsource`, so it works offline). Used for titles, tab labels, lamps, and the ticker.
* **Body and data:** *IBM Plex Mono* for numbers, tool names and logs. The system UI font is used for longer reading text.
* Headings are letter-spaced. Body text is 14–15px with relaxed line height.

## 4. Pixel details

* Panels have a 1px border plus a 2px stepped "pixel corner" (via `clip-path`) instead of round corners.
* There's a faint scanline overlay on the page (2% opacity), turned off for reduced motion.
* Icons and sprites are drawn from 16×16 pixel grids as SVG, with `shape-rendering: crispEdges`.

## 5. The party (agents)

Every character is an original design. The boss is an original horned beast-king. It is **not** based on any existing game character.

| Agent | Name | Look (16×16 sprite) | Personality | Voice |
|---|---|---|---|---|
| Boss | **King Grimhorn** | Horned beast-king: curled bone horns, gold crown, heavy brow, glowing eyes, little fangs, violet scales | Big, gruff, theatrical, but fair. Hates waste and loves a decision. Breaks every tie. | "GRRAH. Report!" / "Decision made. Next!" |
| Inventory | **Pip Stockwell** | Young clerk in a teal cap, holding a clipboard | Quick, eager, counts everything twice | "On it! Counting now…" |
| Accounting | **Ada Ledger** | Tidy accountant with round glasses and a neat bun | Precise, calm, and protective of every dollar | "Let me check the numbers." |
| Facilities | **Bo Brickley** | Builder in a copper hard hat, with a wrench | Laid-back and practical. Knows the building inside out | "Rent's my beat. I'll handle it." |
| Customer service | **Sunny Vale** | Friendly face with a headset and rosy cheeks | Warm and clear. Never promises what isn't approved | "I'll write them something kind." |

Personality lines are **flavor only** and only shown as status chatter ("On it!"). Every fact on screen (stock, cash, prices, decisions) comes from the backend, which gets it from `campus_customs_new.db` through the MCP server. Nothing is made up.

## 6. Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ CAMPUS CUSTOMS · COMMAND DECK     [🔊] [⚑ 0 decisions]  ▸ CHECKING $160.00 ◂│  ← ticker, top right
├────────────────────────────────────────────────────────────────────────┤
│ [ HOME ] [ #101 ] [ #102 ] [ #103 ] [ #104 ] … [ LEADERBOARD ]            │  ← tabs (one per ticket)
├────────────────────────────────────────────────────────────────────────┤
│  tab content                                                            │
└────────────────────────────────────────────────────────────────────────┘
```

### Home (the snapshot)
* **Stat tiles:** total tickets, open, waiting on Majid, closed, cash, and tokens used.
* **Party status:** all five agents with their sprite and a lamp: idle (dim), working (yellow, pulsing), or done in the current run (green).
* **Quest board:** every ticket as a card with a status pill and a "Start mission" button. The admin picks which ticket the team starts on.
* **Decisions waiting:** count of pending approvals, with a button that opens the approval dialog.
* **Last mission:** the outcome of the latest run.

### Ticket tab (one per ticket)
* **Quest header:** subject, requester, item, links, and status.
* **Mission lamps:** five round lamps in a row: *Read ticket → Inventory check → Team work → Boss decision → Closed*. Each goes red → yellow → green and stays green.
* **The arena:** the boss sits in the center with the four specialists around him. When one agent talks to another, a glowing beam travels between them. Each agent's latest line appears in a speech bubble in their color, and a lamp under each sprite shows their state. A side log lists the conversation in order: who asked whom, what they asked, and what came back.
* **Mission report** (after the run): the final decision, the status, and a card per agent showing what they did (tools used, changes made, their own summary).
* **Replay:** any past run of this ticket can be replayed in the arena, step by step.

### Leaderboard tab
* A ranked table of the five agents: level, XP bar, missions, tasks completed, actions taken, tool calls, hand-offs received, drafts, approvals requested, risk flags, and tickets closed.
* **XP formula:** +25 per ticket closed in a mission they joined, +10 per task completed, +5 per action that changed something, +3 per hand-off received, +1 per tool call. Level = 1 + XP ÷ 100.

## 7. Decisions (human approval)

* When a payment, purchase order, or promotion is waiting, a dialog opens on its own (once per item), styled as a "Decision" card in the arcade style.
* It shows what it is, how much, who asked, why, and the **cash after**. If cash would go negative, a red line says the payment will be refused.
* The buttons are **Approve** and **Reject**, with a name field (default "Majid") and a confirm step. The dialog can be dismissed and reopened from the header badge.
* Approvals go through the backend to the MCP server's human-only command. No agent can approve anything.

## 8. Closing a ticket

* When a run finishes and the boss's outcome is `shipped` or `resolved`, the backend marks the ticket **resolved**. If the outcome is waiting for Majid or blocked, the ticket stays as is, and the dialog or alert tells him what's needed. A ticket is never marked resolved while it waits for a human.
* Each time a ticket turns resolved: full-screen pixel **fireworks** for about 3 seconds, a short **chiptune fanfare** (square-wave arpeggio, synthesized in the browser, no audio files), and a "QUEST CLEAR" banner.
* For reduced motion there's a static banner, and the sound still respects mute.

## 9. Motion

* Lamps: yellow pulses slowly (1.6s). Green fades in once, then holds.
* Beams: a 1.2s glow that travels from the speaker to the listener.
* Speech bubbles: fade in, 200ms.
* The ticker scrolls slowly (about 30s per loop). The balance flashes ice-blue once whenever it changes.

## 10. Accessibility

* Text contrast is at least 4.5:1 against the panels.
* Every lamp has a text label for screen readers ("Inventory check: done").
* Everything works with the keyboard. Tabs use `role="tab"`, and the dialog traps focus and closes with Esc.

## 11. Why we chose this design

| Choice | Why |
|---|---|
| **A game frame** (quests, party, missions, decisions) | A multi-agent run is hard to follow as a log. Treating tickets as quests and agents as characters makes "who is doing what" readable at a glance, and it makes Majid's approvals feel like the player's move, which is exactly what they are. |
| **Calm 80s pixel style, mostly blue and grey** | The retro look gives the deck personality without competing with the data. Blue and grey keep it calm for long runs, so the few accent colors (lamps, agent colors, red warnings) stand out where they matter. |
| **Red → yellow → green lamps that stay green** | Progress you can read from across the room. Lamps never go back to red, so a finished step never looks unfinished. |
| **One fixed color per agent** | The same color on sprite, name, bubble, report card, and leaderboard row lets you track an agent across every view without reading names. |
| **The arena with beams and a "who said what" log** | Hand-offs are the point of a team. Beams show *who asked whom*, and the log shows *what was said*, so delegation can be checked against the Expected plan. |
| **Decision dialog that opens on its own and shows "cash after"** | Human approval is required for every payment. The dialog makes the pending decision impossible to miss, and showing the balance after payment (with a red line if it would go negative) helps Majid decide safely. |
| **Checking ticker in the top-right** | Cash is the one number every ticket affects, so it stays visible on every tab and flashes when it changes. |
| **Home snapshot plus one tab per ticket** | Home answers "where are things?" in one look; each ticket tab answers "what happened here?" in depth, including a replay of past runs. |
| **Fireworks and a chiptune on close** | A clear, rewarding signal that a ticket is truly resolved. It's short, and it respects mute and reduced motion. |
| **Original characters only** | The boss is an original beast-king rather than a copy of an existing game character, so the deck has its own identity. |
| **Facts only from the backend** | Personality lines are flavor. Every number on screen comes from `campus_customs_new.db` through MCP, so the deck never shows something the agents or the database didn't actually report. |

## 12. Data sources (all at `http://localhost:8000`)

| Route | Used for |
|---|---|
| `GET /api/health` | Connection light |
| `GET /api/summary` | Home snapshot |
| `GET /api/tickets?all=true` | Every ticket, and the tabs |
| `POST /api/tickets` | (available; the intake form is not shown on the deck) |
| `POST /api/tickets/{id}/run` | Start a mission |
| `GET /api/runs/current` | Is a mission running |
| `GET /api/runs` | Past missions, per ticket |
| `GET /api/runs/{run_id}/summary` | Mission report: what each agent did |
| `GET /api/events?run_id=` | Live arena feed |
| `GET /api/approvals`, `POST /api/approvals/{kind}/{id}` | Decisions |
| `GET /api/cash` | The ticker |
| `POST /api/reset` | Human-only database reset before a full run (needs `"confirm": "RESET"`; not exposed as a deck button) |
| `GET /api/board` | Drafts and notes per ticket |
| `GET /api/leaderboard` | Leaderboard |
