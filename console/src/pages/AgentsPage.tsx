import { LedgerSection, PageHeading, StatusMark } from "../components/Primitives";
import type { PageProps } from "./shared";

export function AgentsPage({ profile, agents, selectedAgent, onNavigate }: PageProps) {
  const current = agents.find((agent) => agent.agent_id === selectedAgent) || agents[0];
  return <div className="page page-enter">
    <PageHeading eyebrow="01 / DELEGATION REGISTER" title="我的 Agent" summary="这里展示真实的人→Agent→工具→数据域授权链。每次调用仍会实时核对 assignment，不依赖 token 过期。" action={<button className="primary-action" onClick={() => onNavigate("ticket")}>委托发起工单</button>} />
    <LedgerSection number="A" title="当前身份链" aside={<span className="document-ref">REG / {profile.assignment_version.toString().padStart(4, "0")}</span>}>
      <div className="identity-chain">
        <div className="chain-node human"><span>HUMAN</span><b>{profile.username}</b><small>{profile.subject}</small></div>
        <div className="chain-link"><i/><span>有效 assignment</span></div>
        <div className="chain-node agent"><span>AGENT</span><b>{current?.name || "未分配"}</b><small>{current?.agent_id || "—"}</small></div>
        <div className="chain-link"><i/><span>YAML ceiling</span></div>
        <div className="chain-node scope"><span>SCOPE</span><b>{current?.tools.length || 0} 工具 / {current?.data_domains.length || 0} 数据域</b><small>六关执行前再次授权</small></div>
      </div>
    </LedgerSection>
    <LedgerSection number="B" title="授权明细" aside={<StatusMark value="active" />}>
      <div className="split-register">
        <div><h3>可调用工具</h3><div className="scope-list">{current?.tools.map((tool) => <span key={tool}>{tool}</span>) || <em>无</em>}</div></div>
        <div><h3>可访问数据域</h3><div className="scope-list domains">{current?.data_domains.map((domain) => <span key={domain}>{domain}</span>) || <em>无</em>}</div></div>
      </div>
    </LedgerSection>
    <LedgerSection number="C" title="全部可委托 Agent">
      <div className="agent-register header"><span>Agent</span><span>能力边界</span><span>数据边界</span><span>版本</span></div>
      {agents.map((agent) => <div className={`agent-register ${agent.agent_id === selectedAgent ? "selected" : ""}`} key={agent.agent_id}>
        <span><b>{agent.name}</b><code>{agent.agent_id}</code></span><span>{agent.tools.join(" · ")}</span><span>{agent.data_domains.join(" · ")}</span><span>v{agent.assignment_version}</span>
      </div>)}
    </LedgerSection>
  </div>;
}

