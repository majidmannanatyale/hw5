import { useEffect, useRef, useState } from "react";
import { api, money, type ApprovalItem, type ApprovalKind, type Approvals } from "./api";
import { nameOf, colorOf } from "./agents";

type Row = { kind: ApprovalKind; item: ApprovalItem; title: string; tag: string };

export function rowsOf(a: Approvals | null): Row[] {
  if (!a) return [];
  return [
    ...a.payments.map(p => ({ kind: "payment" as const, item: p, tag: "PAYMENT",
      title: `Pay ${money(p.amount)} for ${p.kind} #${p.ref_id}` })),
    ...a.purchase_orders.map(p => ({ kind: "po" as const, item: p, tag: "PURCHASE",
      title: `Buy ${p.qty} × ${p.sku} ${p.size} for ${money(p.amount)}` })),
    ...a.promotions.map(p => ({ kind: "promo" as const, item: p, tag: "PROMOTION",
      title: `${p.discount_pct}% off ${p.sku}${(p.min_qty ?? 1) > 1 ? ` for ${p.min_qty}+` : ""}` })),
  ];
}

export function ApprovalModal({ approvals, cash, onClose, onDone }: {
  approvals: Approvals | null; cash: number; onClose: () => void; onDone: () => void;
}) {
  const rows = rowsOf(approvals);
  const [who, setWho] = useState("Majid");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    box.current?.querySelector<HTMLElement>("button, input")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && box.current) {  // keep focus inside the dialog
        const f = [...box.current.querySelectorAll<HTMLElement>("button:not(:disabled), input")];
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const decide = async (r: Row, approve: boolean) => {
    if (!who.trim()) { setErr("Type your name first."); return; }
    if (!window.confirm(`${approve ? "APPROVE" : "REJECT"}: ${r.title}\nRecorded as ${who.trim()}.`)) return;
    setBusy(`${r.kind}${r.item.id}`); setErr(null);
    try { await api.decide(r.kind, r.item.id, approve, who.trim()); onDone(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(null); }
  };

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal panel" role="dialog" aria-modal="true" aria-labelledby="dlg-title" ref={box} onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h2 id="dlg-title">⚑ DECISION NEEDED</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <p className="muted">Only you can approve money leaving the shop. The agents are waiting on your call.</p>
        <label className="who">Deciding as <input value={who} onChange={e => setWho(e.target.value)} maxLength={40} /></label>
        {err && <p className="err" role="alert">{err}</p>}
        {rows.length === 0 && <p className="muted">All clear. Nothing is waiting.</p>}
        {rows.map(r => {
          const cost = r.kind === "promo" ? 0 : r.item.amount ?? 0;
          const after = cash - cost;
          const id = `${r.kind}${r.item.id}`;
          return (
            <article key={id} className="decision">
              <span className="tag">{r.tag} #{r.item.id}</span>
              <strong className="dec-title">{r.title}</strong>
              <p className="small">Asked by <b style={{ color: colorOf(r.item.requested_by) }}>{nameOf(r.item.requested_by)}</b>
                {r.item.reason ? ` · ${r.item.reason}` : ""}{r.item.ticket_id ? ` · quest #${r.item.ticket_id}` : ""}
                {r.item.eta ? ` · arrives ${r.item.eta} if approved` : ""}</p>
              {r.kind !== "promo" && (
                <p className={`small ${after < 0 ? "neg" : "muted"}`}>
                  Checking {money(cash)} → {money(after)}{after < 0 ? " · not enough cash: approving will be refused" : ""}
                </p>)}
              <div className="dec-actions">
                <button className="btn" disabled={busy === id} onClick={() => decide(r, false)}>Reject</button>
                <button className="btn btn-primary" disabled={busy === id} onClick={() => decide(r, true)}>
                  {busy === id ? "Working…" : "Approve"}</button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
