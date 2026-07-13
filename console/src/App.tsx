import { useEffect, useRef, useState } from "react";
import { ControlApi } from "./api";
import { initializeIdentity, loadPublicConfig, type IdentitySession } from "./auth";
import { Shell } from "./components/Shell";
import { ErrorNotice } from "./components/Primitives";
import { AgentsPage } from "./pages/AgentsPage";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { EffectsPage } from "./pages/EffectsPage";
import { EvidencePage } from "./pages/EvidencePage";
import { TicketPage } from "./pages/TicketPage";
import type { AgentAssignment, UserProfile, ViewId } from "./types";

function BootScreen({ error }: { error?: unknown }) {
  return <div className="boot-screen"><div className="boot-grid"/><div className="boot-lock"><span>XA</span><i /></div><p>正在建立可信身份链</p><h1>PERSON → AGENT → EFFECT</h1>{error ? <ErrorNotice error={error} /> : <div className="boot-progress"><i /></div>}</div>;
}

export default function App() {
  const [session, setSession] = useState<IdentitySession>();
  const [api, setApi] = useState<ControlApi>();
  const [profile, setProfile] = useState<UserProfile>();
  const [agents, setAgents] = useState<AgentAssignment[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const selectedAgentRef = useRef("");
  const [view, setView] = useState<ViewId>("agents");
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const config = await loadPublicConfig();
        const identity = await initializeIdentity(config);
        selectedAgentRef.current = config.defaultAgentId;
        const client = new ControlApi(config.apiBasePath, identity.getToken, () => selectedAgentRef.current);
        const [me, delegated] = await Promise.all([client.me(), client.agents()]);
        const available = delegated.items;
        const resolved = available.some((item) => item.agent_id === selectedAgentRef.current)
          ? selectedAgentRef.current : available[0]?.agent_id || "";
        selectedAgentRef.current = resolved;
        if (alive) {
          setSession(identity); setApi(client); setProfile(me); setAgents(available); setSelectedAgent(resolved);
        }
      } catch (reason) { if (alive) setError(reason); }
    })();
    return () => { alive = false; };
  }, []);

  const chooseAgent = (agentId: string) => { selectedAgentRef.current = agentId; setSelectedAgent(agentId); };
  if (!session || !api || !profile) return <BootScreen error={error} />;
  const common = { api, profile, agents, selectedAgent, onNavigate: setView };
  return <Shell view={view} onView={setView} profile={profile} agents={agents} selectedAgent={selectedAgent} onAgent={chooseAgent} onLogout={session.logout}>
    {view === "agents" && <AgentsPage {...common} />}
    {view === "ticket" && <TicketPage {...common} />}
    {view === "effects" && <EffectsPage {...common} />}
    {view === "approvals" && <ApprovalsPage {...common} />}
    {view === "assignments" && <AssignmentsPage {...common} />}
    {view === "evidence" && <EvidencePage {...common} />}
  </Shell>;
}

