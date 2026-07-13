import type { AgentAssignment, UserProfile, ViewId } from "../types";
import type { ReactNode } from "react";
import { Icon } from "./Icons";

const navigation: Array<{ id: ViewId; label: string; caption: string }> = [
  { id: "agents", label: "我的 Agent", caption: "IDENTITY CHAIN" },
  { id: "ticket", label: "发起工单", caption: "CONTROLLED ACTION" },
  { id: "effects", label: "操作影响", caption: "EFFECT LEDGER" },
  { id: "approvals", label: "待我审批", caption: "DUAL CONTROL" },
  { id: "assignments", label: "身份与 Agent", caption: "ASSIGNMENT" },
  { id: "evidence", label: "审计证据", caption: "EVIDENCE CHAIN" },
];

interface ShellProps {
  view: ViewId;
  onView: (view: ViewId) => void;
  profile: UserProfile;
  agents: AgentAssignment[];
  selectedAgent: string;
  onAgent: (agentId: string) => void;
  onLogout: () => Promise<void>;
  children: ReactNode;
}

export function Shell({ view, onView, profile, agents, selectedAgent, onAgent, onLogout, children }: ShellProps) {
  return <div className="console-shell">
    <aside className="side-rail">
      <div className="wordmark"><span className="seal">XA</span><div><b>XA—GUARD</b><small>可信智能体控制台</small></div></div>
      <div className="rail-rule"><span>CONTROL PLANE / 06</span></div>
      <nav aria-label="主导航">
        {navigation.map((item, index) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => onView(item.id)}>
          <span className="nav-number">0{index + 1}</span><Icon name={item.id} /><span><b>{item.label}</b><small>{item.caption}</small></span>
        </button>)}
      </nav>
      <div className="rail-foot">
        <span className="live-pulse"><i />IDENTITY VERIFIED</span>
        <p>Token storage</p><strong>MEMORY ONLY</strong>
      </div>
    </aside>
    <div className="workbench">
      <header className="identity-bar">
        <div className="identity-principal"><span className="micro-label">当前人员 / HUMAN</span><b>{profile.username}</b><small>{profile.tenant_id} · {profile.subject.slice(0, 12)}…</small></div>
        <div className="delegate-arrow"><span>标准委托</span><Icon name="arrow" /></div>
        <label className="agent-selector"><span className="micro-label">执行主体 / AGENT</span><select value={selectedAgent} onChange={(event) => onAgent(event.target.value)} aria-label="选择已授权 Agent">
          {agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name} · {agent.agent_id}</option>)}
        </select><small>assignment v{profile.assignment_version}</small></label>
        <div className="bar-actions"><span className="role-readout">{profile.roles.join(" / ") || "NO PRIVILEGED ROLE"}</span><button className="icon-button" onClick={() => void onLogout()} title="退出登录"><Icon name="exit" /></button></div>
      </header>
      <main className="paper-plane">{children}</main>
      <footer className="system-footer"><span>XA-202620</span><span>前有身份 · 途中六关 · 后有撤销 · 全程证据</span><span>{new Date().toLocaleDateString("zh-CN")}</span></footer>
    </div>
  </div>;
}
