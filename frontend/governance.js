"use strict";

const state = {
  registry: null,
  records: [],
};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[ch]));
}

function text(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.map((item) => text(item)).join(", ") || "-";
  if (typeof value === "object") return escapeHtml(JSON.stringify(value));
  return escapeHtml(value);
}

function decision(record) {
  const raw = String(record["gen_ai.decision.final"] || "allow").toLowerCase();
  return ["allow", "deny", "require_approval", "warn"].includes(raw) ? raw : "warn";
}

function shortTime(ts) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? text(ts) : d.toLocaleString("zh-CN", { hour12: false });
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.text();
}

function parseJsonl(raw) {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function hasDomain(employee, domain) {
  if ((employee.data_domains || []).includes(domain.domain_id)) return true;
  if ((domain.allowed_departments || []).includes(employee.department)) return true;
  const directRoles = employee.roles || [];
  const boundRoles = state.registry.role_bindings
    .filter((binding) => (binding.principals || []).includes(employee.principal_id)
      || (binding.groups || []).some((group) => (employee.groups || []).includes(group)))
    .map((binding) => binding.role_id);
  return [...directRoles, ...boundRoles].some((role) => (domain.allowed_roles || []).includes(role));
}

function metric(label, value) {
  return `<div class="metric"><span class="metric-value">${text(value)}</span><span class="metric-label">${text(label)}</span></div>`;
}

function renderMetrics() {
  const registry = state.registry;
  const records = state.records;
  const denied = records.filter((record) => decision(record) === "deny").length;
  const approvals = records.filter((record) => decision(record) === "require_approval").length;
  const cost = records.reduce((sum, record) => sum + Number(record["gen_ai.governance.cost_estimate_usd"] || 0), 0);

  document.getElementById("metric-strip").innerHTML = [
    metric("员工", registry.employees.length),
    metric("智能体", registry.agents.length),
    metric("角色 / 策略", `${registry.roles.length} / ${registry.approval_policies.length}`),
    metric("数据域", registry.data_domains.length),
    metric("拦截 / 待审批", `${denied} / ${approvals}`),
    metric("估算成本 USD", cost.toFixed(2)),
  ].join("");
}

function renderScenarios() {
  const records = state.records.filter((record) => record["gen_ai.governance.task_id"]);
  document.getElementById("scenario-summary").textContent = `${records.length} 个演示事件`;
  document.getElementById("scenario-grid").innerHTML = records.map((record) => {
    const d = decision(record);
    const principal = record["gen_ai.governance.human_principal"];
    const agent = record["gen_ai.governance.agent_id"];
    const domain = record["gen_ai.governance.data_domain"];
    const owner = record["gen_ai.governance.resource_owner"];
    const reason = record["gen_ai.decision.final_reason"] || "ok";
    return `
      <article class="scenario ${d}">
        <div class="scenario-title">
          <span>${text(record["gen_ai.governance.task_id"])}</span>
          <span class="badge ${d}">${d.toUpperCase()}</span>
        </div>
        <div class="meta">
          员工：${text(principal)}<br>
          Agent：${text(agent)}<br>
          数据域：${text(domain)} / 资源主体：${text(owner)}<br>
          结果：${text(reason)}
        </div>
      </article>
    `;
  }).join("");
}

function renderAgents() {
  const agents = state.registry.agents;
  document.getElementById("agent-count").textContent = `${agents.length} 个登记 Agent`;
  document.getElementById("agent-table").innerHTML = `
    <thead><tr><th>Agent</th><th>Owner</th><th>允许工具</th><th>允许数据域</th><th>自主级别</th></tr></thead>
    <tbody>
      ${agents.map((agent) => `
        <tr>
          <td><strong>${text(agent.name)}</strong><br><span class="meta">${text(agent.agent_id)}</span></td>
          <td>${text(agent.owner)}</td>
          <td>${(agent.allowed_tools || []).map((item) => `<span class="pill">${text(item)}</span>`).join("")}</td>
          <td>${(agent.allowed_data_domains || []).map((item) => `<span class="pill">${text(item)}</span>`).join("")}</td>
          <td>${text(agent.max_autonomy)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderRoles() {
  const roles = state.registry.roles;
  const policies = state.registry.approval_policies;
  document.getElementById("role-count").textContent = `${roles.length} 个角色 · ${policies.length} 条审批策略`;
  document.getElementById("role-table").innerHTML = `
    <thead><tr><th>角色</th><th>租户</th><th>权限动作</th><th>审批策略</th></tr></thead>
    <tbody>
      ${roles.map((role, idx) => {
        const policy = policies[idx] || {};
        const actions = (role.permissions || []).map((permission) => permission.action);
        return `
          <tr>
            <td><strong>${text(role.name || role.role_id)}</strong><br><span class="meta">${text(role.role_id)}</span></td>
            <td>${text(role.tenant_id)}</td>
            <td>${actions.map((item) => `<span class="pill">${text(item)}</span>`).join("") || "-"}</td>
            <td><strong>${text(policy.policy_id)}</strong><br><span class="meta">${text(policy.reason)}</span></td>
          </tr>
        `;
      }).join("")}
    </tbody>
  `;
}

function renderMatrix() {
  const employees = state.registry.employees;
  const domains = state.registry.data_domains;
  document.getElementById("domain-count").textContent = `${employees.length} 名员工 x ${domains.length} 个数据域`;
  document.getElementById("matrix-table").innerHTML = `
    <thead>
      <tr><th>员工</th>${domains.map((domain) => `<th>${text(domain.name)}<br><span class="meta">${text(domain.domain_id)}</span></th>`).join("")}</tr>
    </thead>
    <tbody>
      ${employees.map((employee) => `
        <tr>
          <td><strong>${text(employee.name)}</strong><br><span class="meta">${text(employee.department)} · ${text(employee.groups || employee.roles)}</span></td>
          ${domains.map((domain) => {
            const ok = hasDomain(employee, domain);
            return `<td class="${ok ? "cell-ok" : "cell-no"}">${ok ? "允许" : "禁止"}</td>`;
          }).join("")}
        </tr>
      `).join("")}
    </tbody>
  `;
}

function renderAudit() {
  const records = [...state.records].sort((a, b) => String(b.timestamp || "").localeCompare(String(a.timestamp || "")));
  document.getElementById("audit-count").textContent = `${records.length} 条审计记录`;
  document.getElementById("audit-list").innerHTML = records.map((record) => {
    const d = decision(record);
    const rawHits = record["gen_ai.policy.hit_id"] || [];
    const hits = Array.isArray(rawHits) ? rawHits : [rawHits];
    return `
      <article class="audit-item">
        <div class="audit-time">${shortTime(record.timestamp)}</div>
        <div class="audit-main">
          <div class="audit-title">${text(record["gen_ai.tool.name"])} · ${text(record["gen_ai.governance.task_id"])}</div>
          <div class="audit-extra">
            ${text(record["gen_ai.governance.human_principal"])} 使用 ${text(record["gen_ai.governance.agent_id"])}
            访问 ${text(record["gen_ai.governance.data_domain"])}
            <br>角色：${text(record["gen_ai.governance.role_ids"])}
            · 原因码：${text(record["gen_ai.governance.decision_reason_code"])}
            <br>命中规则：${hits.map((hit) => `<span class="pill">${text(hit)}</span>`).join("") || "-"}
          </div>
        </div>
        <div><span class="badge ${d}">${d.toUpperCase()}</span></div>
      </article>
    `;
  }).join("");
}

function normalizeRegistry(raw) {
  const employees = raw.principals || raw.employees || [];
  return {
    employees: employees.map((employee) => ({
      ...employee,
      principal_id: employee.principal_id || employee.principal,
      name: employee.display_name || employee.name || employee.principal_id || employee.principal,
    })),
    agents: raw.agents || [],
    data_domains: raw.data_domains || [],
    roles: raw.roles || [],
    role_bindings: raw.role_bindings || [],
    approval_policies: raw.approval_policies || [],
  };
}

async function loadAll() {
  const registryPath = document.getElementById("registry-path").value.trim();
  const auditPath = document.getElementById("audit-path").value.trim();
  const [registryRaw, auditRaw] = await Promise.all([fetchText(registryPath), fetchText(auditPath)]);
  state.registry = normalizeRegistry(JSON.parse(registryRaw));
  state.records = parseJsonl(auditRaw);
  renderMetrics();
  renderScenarios();
  renderAgents();
  renderRoles();
  renderMatrix();
  renderAudit();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("load-btn").addEventListener("click", () => {
    loadAll().catch((error) => {
      document.getElementById("scenario-grid").innerHTML = `<article class="scenario deny">加载失败：${text(error.message)}</article>`;
    });
  });
  loadAll().catch((error) => {
    document.getElementById("scenario-grid").innerHTML = `<article class="scenario deny">加载失败：${text(error.message)}</article>`;
  });
});
