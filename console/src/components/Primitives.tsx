import type { PropsWithChildren, ReactNode } from "react";

export function PageHeading({ eyebrow, title, summary, action }: { eyebrow: string; title: string; summary: string; action?: ReactNode }) {
  return <header className="page-heading">
    <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-summary">{summary}</p></div>
    {action && <div className="page-action">{action}</div>}
  </header>;
}

export function LedgerSection({ number, title, aside, children, className = "" }: PropsWithChildren<{ number: string; title: string; aside?: ReactNode; className?: string }>) {
  return <section className={`ledger-section ${className}`}>
    <div className="section-index">{number}</div>
    <div className="section-body"><div className="section-title"><h2>{title}</h2>{aside}</div>{children}</div>
  </section>;
}

export function StatusMark({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone = ["compensated", "available", "approved", "completed", "open", "active"].includes(normalized) ? "ok"
    : ["manual_required", "compensation_failed", "rejected", "expired", "failed"].includes(normalized) ? "danger"
      : "pending";
  return <span className={`status-mark ${tone}`}><i />{value.replaceAll("_", " ")}</span>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><span>∅</span><strong>{title}</strong><p>{detail}</p></div>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const value = error as { message?: string; detail?: { trace_id?: string } };
  return <div className="error-notice" role="alert"><b>请求未完成</b><span>{value.message || "未知错误"}</span>{value.detail?.trace_id && <code>{value.detail.trace_id}</code>}</div>;
}

export function ShortHash({ value = "" }: { value?: string }) {
  return <code className="short-hash" title={value}>{value ? `${value.slice(0, 10)}…${value.slice(-8)}` : "—"}</code>;
}

