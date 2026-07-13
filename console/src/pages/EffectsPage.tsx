import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNotice, LedgerSection, PageHeading, ShortHash, StatusMark } from "../components/Primitives";
import type { Effect } from "../types";
import { formatTime, remaining, type PageProps } from "./shared";

export function EffectsPage({ api }: PageProps) {
  const [effects, setEffects] = useState<Effect[]>([]);
  const [selected, setSelected] = useState<Effect>();
  const [error, setError] = useState<unknown>();
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    try {
      const value = await api.effects(); setEffects(value.items);
      if (value.items[0]) setSelected(await api.effect(selected?.effect_id || value.items[0].effect_id));
    } catch (reasonValue) { setError(reasonValue); }
  }, [api, selected?.effect_id]);
  useEffect(() => { void load(); }, [api]); // load once for this page instance
  const choose = async (effect: Effect) => { setSelected(effect); setError(undefined); try { setSelected(await api.effect(effect.effect_id)); } catch (reasonValue) { setError(reasonValue); } };
  const undo = async () => {
    if (!selected || !reason.trim()) return;
    setError(undefined);
    try { const value = await api.requestUndo(selected.effect_id, reason.trim()); setNotice(`撤销申请 ${value.request_id} 已进入独立审批队列`); setReason(""); await load(); } catch (reasonValue) { setError(reasonValue); }
  };
  return <div className="page page-enter">
    <PageHeading eyebrow="03 / EFFECT LEDGER" title="操作影响" summary="Effect 不是日志标签，而是补偿系统的事实单元。此页只展示租户内记录，恢复材料始终不可见。" action={<button className="secondary-action" onClick={() => void load()}>刷新台账</button>} />
    <ErrorNotice error={error} />{notice && <div className="success-notice">{notice}</div>}
    <LedgerSection number="A" title="影响台账" aside={<span className="document-ref">{effects.length} EFFECTS</span>}>
      {effects.length === 0 ? <EmptyState title="尚无副作用记录" detail="成功执行带 v2 合同的写工具后，Effect 会出现在这里。" /> : <div className="effect-table"><div className="effect-row header"><span>时间 / Effect</span><span>动作与数据域</span><span>可逆性</span><span>状态</span><span>窗口</span></div>{effects.map((effect) => <button key={effect.effect_id} className={`effect-row ${selected?.effect_id === effect.effect_id ? "selected" : ""}`} onClick={() => void choose(effect)}><span><time>{formatTime(effect.prepared_at)}</time><code>{effect.effect_id}</code></span><span><b>{effect.tool_name}</b><small>{effect.agent_id} · {effect.data_domain}</small></span><span>{effect.reversibility}</span><span><StatusMark value={effect.status} /></span><span>{remaining(effect.undo_expires_at)}</span></button>)}</div>}
    </LedgerSection>
    {selected && <LedgerSection number="B" title="影响剖面" aside={<StatusMark value={selected.status} />}>
      <div className="impact-profile"><dl><dt>原动作 trace</dt><dd><ShortHash value={selected.trace_id} /></dd><dt>下游引用</dt><dd>{selected.downstream_reference || "—"}</dd><dt>结果摘要</dt><dd><ShortHash value={selected.result_sha256} /></dd><dt>补偿 trace</dt><dd><ShortHash value={selected.compensation_trace_id} /></dd><dt>重试次数</dt><dd>{selected.retry_count || 0}</dd><dt>最近错误</dt><dd>{selected.last_error_code || "无"}</dd></dl><div className="impact-scale"><span>原动作</span><i className="active"/><i className={selected.status !== "prepared" ? "active" : ""}/><i className={selected.status === "compensated" ? "active" : ""}/><span>业务恢复</span></div></div>
      {selected.status === "available" && <div className="undo-strip"><label><span>撤销理由</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="理由将摘要入链，审批人与申请人必须不同" /></label><button className="danger-action" disabled={!reason.trim()} onClick={() => void undo()}>发起 Undo</button></div>}
    </LedgerSection>}
  </div>;
}

