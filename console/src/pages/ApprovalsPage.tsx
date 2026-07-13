import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNotice, LedgerSection, PageHeading, StatusMark } from "../components/Primitives";
import type { UndoRequest } from "../types";
import { formatTime, remaining, type PageProps } from "./shared";

export function ApprovalsPage({ api, profile }: PageProps) {
  const [items, setItems] = useState<UndoRequest[]>([]);
  const [selected, setSelected] = useState<string>();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const canApprove = profile.roles.includes("undo.approve");
  const load = useCallback(async () => { setError(undefined); try { setItems((await api.undoRequests("pending")).items); } catch (value) { setError(value); } }, [api]);
  useEffect(() => { if (canApprove) void load(); }, [canApprove, load]);
  const decide = async (decision: "approve" | "reject") => {
    if (!selected || !reason.trim()) return; setBusy(true); setError(undefined);
    try { await api.decide(selected, decision, reason.trim()); setSelected(undefined); setReason(""); await load(); } catch (value) { setError(value); } finally { setBusy(false); }
  };
  return <div className="page page-enter">
    <PageHeading eyebrow="04 / DUAL CONTROL" title="待我审批" summary="这是独立审批人的工作面，不提供角色切换。当前登录者只能以 IdP 已签发的身份和权限作出决定。" action={<span className={`authority-stamp ${canApprove ? "valid" : "invalid"}`}>{canApprove ? "APPROVER VERIFIED" : "NO APPROVER ROLE"}</span>} />
    <ErrorNotice error={error} />
    {!canApprove ? <LedgerSection number="A" title="职责分离"><EmptyState title="当前身份不是审批人" detail="请退出并由独立审批人通过 IdP 登录；本页不会模拟、切换或提升角色。" /></LedgerSection> : <>
      <LedgerSection number="A" title="待决队列" aside={<span className="document-ref">QUEUE / {items.length}</span>}>
        {items.length === 0 ? <EmptyState title="队列已清" detail="没有等待当前租户审批的 Undo 请求。" /> : <div className="approval-register">{items.map((item) => <button key={item.request_id} className={selected === item.request_id ? "selected" : ""} onClick={() => setSelected(item.request_id)}><span className="approval-check">{selected === item.request_id ? "×" : ""}</span><span><small>REQUEST</small><code>{item.request_id}</code></span><span><small>申请人</small><b>{item.requester_username}</b></span><span><small>目标动作</small><b>{item.tool_name}</b><code>{item.effect_id}</code></span><span><small>申请时间</small>{formatTime(item.requested_at)}</span><span><small>剩余窗口</small><strong>{remaining(item.undo_expires_at)}</strong></span><StatusMark value={item.status} /></button>)}</div>}
      </LedgerSection>
      {selected && <LedgerSection number="B" title="审批意见"><div className="decision-desk"><label><span>决定理由 / REQUIRED</span><textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="说明批准恢复或拒绝的业务依据" /></label><div><button className="secondary-action" disabled={busy || !reason.trim()} onClick={() => void decide("reject")}>拒绝</button><button className="danger-action" disabled={busy || !reason.trim()} onClick={() => void decide("approve")}>批准补偿</button></div></div><p className="decision-warning">批准后 Worker 将使用内部签名授权重新经过 Governance 与 Gate1–6；不会重放你的 JWT。</p></LedgerSection>}
    </>}
  </div>;
}

