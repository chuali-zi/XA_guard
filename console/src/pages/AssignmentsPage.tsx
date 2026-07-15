import { useCallback, useEffect, useState, type FormEvent } from "react";
import { EmptyState, ErrorNotice, LedgerSection, PageHeading, StatusMark } from "../components/Primitives";
import type { Assignment } from "../types";
import { formatTime, type PageProps } from "./shared";

export function AssignmentsPage({ api, profile, agents }: PageProps) {
  const [items, setItems] = useState<Assignment[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const canGovern = profile.roles.includes("governance.admin");
  const firstAgent = agents[0];
  const [form, setForm] = useState({ subject_type: "human", subject_id: "", agent_id: firstAgent?.agent_id || "", tools: firstAgent?.tools.join(", ") || "", data_domains: firstAgent?.data_domains.join(", ") || "", valid_until: "" });
  const load = useCallback(async () => { setError(undefined); try { setItems((await api.assignments()).items); } catch (value) { setError(value); } }, [api]);
  useEffect(() => { if (canGovern) void load(); }, [canGovern, load]);
  const updateAgent = (agentId: string) => { const agent = agents.find((item) => item.agent_id === agentId); setForm((value) => ({ ...value, agent_id: agentId, tools: agent?.tools.join(", ") || "", data_domains: agent?.data_domains.join(", ") || "" })); };
  const create = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(undefined);
    try { await api.createAssignment({ ...form, tools: form.tools.split(",").map((v) => v.trim()).filter(Boolean), data_domains: form.data_domains.split(",").map((v) => v.trim()).filter(Boolean), valid_until: form.valid_until || null }); setForm((v) => ({ ...v, subject_id: "", valid_until: "" })); await load(); } catch (value) { setError(value); } finally { setBusy(false); }
  };
  const revoke = async (item: Assignment) => { if (!window.confirm(`确认撤销 ${item.subject_id} → ${item.agent_id} 的 v${item.version} assignment？`)) return; try { await api.deleteAssignment(item.assignment_id, item.version); await load(); } catch (value) { setError(value); } };
  return <div className="page page-enter">
    <PageHeading eyebrow="05 / ASSIGNMENT CONTROL" title="身份与 Agent" summary="管理员只能在静态 YAML ceiling 内收窄授权。数据库 assignment 带版本、生效期和变更人，撤销立即生效。" action={<span className={`authority-stamp ${canGovern ? "valid" : "invalid"}`}>{canGovern ? "GOVERNANCE ADMIN" : "READ DENIED"}</span>} />
    <ErrorNotice error={error} />
    {!canGovern ? <LedgerSection number="A" title="权限边界"><EmptyState title="无治理管理员权限" detail="本控制台不提供角色切换。请由具有 governance.admin 的独立账号登录。" /></LedgerSection> : <>
      <LedgerSection number="A" title="新增授权" aside={<span className="ceiling-note">不得突破 AGENT CEILING</span>}><form className="assignment-form" onSubmit={(event) => void create(event)}><label className="field"><span>主体类型</span><select value={form.subject_type} onChange={(e) => setForm((v) => ({ ...v, subject_type: e.target.value }))}><option value="human">人员</option><option value="group">Keycloak Group</option></select></label><label className="field"><span>主体 ID</span><input required value={form.subject_id} onChange={(e) => setForm((v) => ({ ...v, subject_id: e.target.value }))} /></label><label className="field"><span>Agent</span><select value={form.agent_id} onChange={(e) => updateAgent(e.target.value)}>{agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name}</option>)}</select></label><label className="field wide"><span>工具（逗号分隔）</span><input required value={form.tools} onChange={(e) => setForm((v) => ({ ...v, tools: e.target.value }))} /></label><label className="field wide"><span>数据域（逗号分隔）</span><input required value={form.data_domains} onChange={(e) => setForm((v) => ({ ...v, data_domains: e.target.value }))} /></label><label className="field"><span>失效时间</span><input type="datetime-local" value={form.valid_until} onChange={(e) => setForm((v) => ({ ...v, valid_until: e.target.value }))} /></label><button className="primary-action" disabled={busy}>{busy ? "正在校验 ceiling…" : "写入授权"}</button></form></LedgerSection>
      <LedgerSection number="B" title="动态授权矩阵" aside={<span className="document-ref">{items.length} ACTIVE</span>}>{items.length === 0 ? <EmptyState title="没有动态授权" detail="YAML 只定义上限；实际可用关系需要写入 assignment。" /> : <div className="assignment-matrix"><div className="matrix-row header"><span>主体</span><span>Agent</span><span>工具 / 数据域</span><span>有效期</span><span>版本</span><span /></div>{items.map((item) => <div className="matrix-row" key={item.assignment_id}><span><b>{item.subject_id}</b><small>{item.subject_type}</small></span><span><code>{item.agent_id}</code></span><span><b>{item.tools.join(" · ")}</b><small>{item.data_domains.join(" · ")}</small></span><span>{item.valid_until ? formatTime(item.valid_until) : "长期有效"}</span><span><StatusMark value={`v${item.version}`} /></span><span><button className="text-action danger-text" onClick={() => void revoke(item)}>撤销</button></span></div>)}</div>}</LedgerSection>
    </>}
  </div>;
}
