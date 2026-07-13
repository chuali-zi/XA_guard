import { useState, type FormEvent } from "react";
import { ErrorNotice, LedgerSection, PageHeading, ShortHash, StatusMark } from "../components/Primitives";
import type { TicketResult } from "../types";
import type { PageProps } from "./shared";

export function TicketPage({ api, agents, selectedAgent, onNavigate }: PageProps) {
  const agent = agents.find((item) => item.agent_id === selectedAgent);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [result, setResult] = useState<TicketResult>();
  const [form, setForm] = useState({ title: "", description: "", priority: "normal", record_id: "", data_domain: agent?.data_domains[0] || "engineering_docs" });
  const update = (name: string, value: string) => setForm((current) => ({ ...current, [name]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(undefined);
    try { setResult(await api.createTicket(form)); } catch (reason) { setError(reason); } finally { setBusy(false); }
  };
  return <div className="page page-enter">
    <PageHeading eyebrow="02 / CONTROLLED ACTION" title="发起工单" summary="人员令牌由 BFF 换取指定 Agent 的短期令牌；浏览器看不到交换结果。写操作先登记 Effect intent，再触达业务 API。" />
    <div className="form-ledger">
      <LedgerSection number="A" title="工单内容" className="form-main">
        <form onSubmit={(event) => void submit(event)}>
          <label className="field wide"><span>标题 / TITLE</span><input required maxLength={120} value={form.title} onChange={(e) => update("title", e.target.value)} placeholder="例：撤销误开通的项目权限" /></label>
          <label className="field wide"><span>事实与处置要求 / DESCRIPTION</span><textarea required maxLength={2000} rows={7} value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="描述业务事实，不要填入密钥或原始 token。" /></label>
          <div className="field-row"><label className="field"><span>优先级</span><select value={form.priority} onChange={(e) => update("priority", e.target.value)}><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label><label className="field"><span>关联记录</span><input value={form.record_id} onChange={(e) => update("record_id", e.target.value)} placeholder="可选" /></label></div>
          <label className="field"><span>数据域</span><select value={form.data_domain} onChange={(e) => update("data_domain", e.target.value)}>{agent?.data_domains.map((domain) => <option key={domain}>{domain}</option>)}</select></label>
          <ErrorNotice error={error} />
          <div className="form-submit"><span>提交即进入 XA-Guard 六关，拒绝发生在业务 API 之前。</span><button className="primary-action" disabled={busy}>{busy ? "正在过六关…" : "确认委托并执行"}</button></div>
        </form>
      </LedgerSection>
      <aside className="execution-docket"><span className="docket-label">EXECUTION DOCKET</span><h2>执行票据</h2><dl><dt>人员</dt><dd>当前登录身份</dd><dt>Agent</dt><dd>{agent?.name}<code>{selectedAgent}</code></dd><dt>副作用</dt><dd>HIGH / COMPENSATABLE</dd><dt>补偿窗口</dt><dd>由合同 v2 决定</dd><dt>数据库先决</dt><dd>prepared 成功才调用下游</dd></dl><div className="six-gates">{[1,2,3,4,5,6].map((gate) => <i key={gate}>{gate}</i>)}</div></aside>
    </div>
    {result && <LedgerSection number="B" title="执行回执" aside={<StatusMark value={result.undo_status} />}><div className="receipt"><div><span>EFFECT ID</span><b>{result.effect_id}</b></div><div><span>TRACE</span><ShortHash value={result.trace_id} /></div><div><span>STATUS</span><b>{result.status}</b></div><button className="text-action" onClick={() => onNavigate("effects")}>查看操作影响 →</button></div></LedgerSection>}
  </div>;
}
