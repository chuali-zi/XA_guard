import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNotice, LedgerSection, PageHeading, ShortHash, StatusMark } from "../components/Primitives";
import type { Effect } from "../types";
import { formatTime, type PageProps } from "./shared";

export function EvidencePage({ api }: PageProps) {
  const [effects, setEffects] = useState<Effect[]>([]);
  const [detail, setDetail] = useState<Effect>();
  const [error, setError] = useState<unknown>();
  const load = useCallback(async () => { try { const value = await api.effects(); setEffects(value.items); if (value.items[0]) setDetail(await api.effect(value.items[0].effect_id)); } catch (reason) { setError(reason); } }, [api]);
  useEffect(() => { void load(); }, [load]);
  const choose = async (effectId: string) => { try { setDetail(await api.effect(effectId)); } catch (reason) { setError(reason); } };
  const events = detail?.events || [];
  // The API returns one Effect's projection from a tenant-wide chain. Its first
  // event can therefore point to a predecessor outside this projection. Verify
  // only the links that are actually present instead of reporting a false gap.
  const chainSegmentComplete = events.length > 0 && events.every(
    (event, index) => index === 0 || event.prev_hash === events[index - 1].record_hash,
  );
  return <div className="page page-enter evidence-page">
    <PageHeading eyebrow="06 / EVIDENCE CHAIN" title="审计证据" summary="把人员身份、Agent、原动作 trace、审批、补偿 trace 与 Effect 事件链放在同一证据面。缺失字段会明确显示，不做推断。" action={<button className="secondary-action" onClick={() => window.print()}>打印当前证据</button>} />
    <ErrorNotice error={error} />
    <div className="evidence-switcher"><span>选择 Effect</span><select value={detail?.effect_id || ""} onChange={(e) => void choose(e.target.value)}>{effects.map((effect) => <option value={effect.effect_id} key={effect.effect_id}>{effect.effect_id} · {effect.tool_name}</option>)}</select></div>
    {!detail ? <EmptyState title="没有可封存证据" detail="执行一次受合同保护的业务写操作后再查看。" /> : <>
      <LedgerSection number="A" title="证据封面" aside={<span className={`chain-verdict ${chainSegmentComplete ? "pass" : "fail"}`}>{chainSegmentComplete ? "CHAIN SEGMENT CONTINUOUS" : "CHAIN GAP"}</span>}><div className="evidence-cover"><div className="evidence-title"><span>XA-GUARD / EFFECT EVIDENCE</span><b>{detail.effect_id}</b><p>{detail.tool_name} · {detail.data_domain}</p></div><dl><dt>人员</dt><dd>{detail.principal_username}<code>{detail.principal_sub}</code></dd><dt>Agent</dt><dd>{detail.agent_id}</dd><dt>原动作 trace</dt><dd><ShortHash value={detail.trace_id} /></dd><dt>补偿 trace</dt><dd><ShortHash value={detail.compensation_trace_id} /></dd><dt>业务引用</dt><dd>{detail.downstream_reference || "未返回"}</dd><dt>最终状态</dt><dd><StatusMark value={detail.status} /></dd></dl><div className="evidence-seal">EFFECT<br/>VERIFIED<small>LOCAL VIEW</small></div></div></LedgerSection>
      <LedgerSection number="B" title="事件时间轨" aside={<span className="document-ref">{events.length} EVENTS</span>}><div className="event-track">{events.map((event, index) => <div className="event-entry" key={event.seq}><div className="event-axis"><i>{index + 1}</i><span /></div><div><time>{formatTime(event.occurred_at)}</time><h3>{event.event_type.replaceAll("_", " ")}</h3><p>actor · {event.actor_sub}</p><div className="hash-pair"><span>PREV <ShortHash value={event.prev_hash} /></span><span>RECORD <ShortHash value={event.record_hash} /></span></div></div></div>)}</div></LedgerSection>
      <LedgerSection number="C" title="封存清单"><div className="manifest-lines"><span><i className={detail.trace_id ? "yes" : "no"}/><b>原动作 Gate6 trace</b><em>{detail.trace_id ? "已关联" : "缺失"}</em></span><span><i className={events.length ? "yes" : "no"}/><b>Effect event chain</b><em>{events.length ? `${events.length} 条` : "缺失"}</em></span><span><i className={detail.compensation_trace_id ? "yes" : "no"}/><b>补偿 Gate6 trace</b><em>{detail.compensation_trace_id ? "已关联" : "尚未发生"}</em></span><span><i className={detail.downstream_reference ? "yes" : "no"}/><b>业务前后态引用</b><em>{detail.downstream_reference || "未返回"}</em></span><span><i className="no"/><b>Artifact manifest 外部封存</b><em>需由验收脚本生成</em></span></div></LedgerSection>
    </>}
  </div>;
}
