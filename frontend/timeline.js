/**
 * XA-Guard 审计回放时间线 - timeline.js
 * ES2020 + vanilla JS, 无外部依赖, 离线可用
 *
 * 主要职责：
 *  - fetch JSONL（ReadableStream 逐行）或 File API 拖拽上传
 *  - 解析 AuditRecord（OTel GenAI key 格式，14 字段）
 *  - 按 timestamp 倒序渲染时间线卡片
 *  - verifyChain() 比对 hash_prev == 前一条 record_hash
 *  - 统计 totalCount / denyCount / warnCount / traceCount
 */

"use strict";

// ============================================================
// 常量
// ============================================================
const REQUIRED_FIELDS = [
  "trace_id",
  "span_id",
  "timestamp",
  "gen_ai.tool.name",
  "gen_ai.tool.parameters",
  "gen_ai.tool.result.hash",
  "gen_ai.user.role",
  "gen_ai.data.sensitivity_level",
  "gen_ai.policy.hit_id",
  "gen_ai.evidence.hash_prev",
  "record_hash",
];

const ALL_FIELDS = [
  "trace_id",
  "span_id",
  "timestamp",
  "gen_ai.request.model",
  "gen_ai.usage.input_tokens",
  "gen_ai.tool.name",
  "gen_ai.tool.parameters",
  "gen_ai.tool.result.hash",
  "gen_ai.user.role",
  "gen_ai.data.sensitivity_level",
  "gen_ai.policy.hit_id",
  "gen_ai.tool.approval_token",
  "gen_ai.evidence.hash_prev",
  "gen_ai.classify.risk_tag",
  "gen_ai.decision.faithfulness_score",
  "record_hash",
  "signature",
];

const DECISION_LABEL = {
  allow:            "ALLOW",
  warn:             "WARN",
  deny:             "DENY",
  require_approval: "REQUIRE_APPROVAL",
  ALLOW:            "ALLOW",
  WARN:             "WARN",
  DENY:             "DENY",
  REQUIRE_APPROVAL: "REQUIRE_APPROVAL",
};

const DECISION_TEXT = {
  ALLOW:            "允许",
  WARN:             "警告",
  DENY:             "拒绝",
  REQUIRE_APPROVAL: "待审批",
};

// ============================================================
// 工具函数
// ============================================================

/**
 * 将值格式化为可读字符串（对象/数组转 JSON）
 */
function formatValue(val) {
  if (val === null || val === undefined) return "";
  if (typeof val === "object") return JSON.stringify(val, null, 2);
  return String(val);
}

/**
 * 截取哈希前 N 位显示
 */
function shortHash(hash, n = 16) {
  if (!hash) return "(空)";
  return hash.slice(0, n);
}

/**
 * 格式化时间戳为本地时间字符串
 */
function formatTs(ts) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d)) return ts;
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return ts;
  }
}

/**
 * 推断 decision 字段（兼容大小写、下划线/空格）
 */
function inferDecision(rec) {
  const raw = rec.decision || rec["gen_ai.decision"] || "";
  return DECISION_LABEL[raw.toUpperCase()] || DECISION_LABEL[raw] || "ALLOW";
}

// ============================================================
// 解析 JSONL
// ============================================================

/**
 * 解析单行 JSON 为审计记录
 * @param {string} line
 * @returns {{record: object|null, error: string|null}}
 */
function parseLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return { record: null, error: null };
  try {
    const rec = JSON.parse(trimmed);
    return { record: rec, error: null };
  } catch (e) {
    return { record: null, error: `JSON 解析错误: ${e.message}` };
  }
}

// ============================================================
// 哈希链验证
// ============================================================

/**
 * 对已按原始顺序（时间升序）排列的记录列表验证哈希链。
 * 返回 Map<number_index, boolean>（true=链正确，false=断链，null=第一条无需验证）
 * @param {object[]} records - 原始顺序记录
 * @returns {Map<number, boolean|null>}
 */
function verifyChain(records) {
  const result = new Map();
  let prevHash = "";
  for (let i = 0; i < records.length; i++) {
    const rec = records[i];
    const hashPrev = rec["gen_ai.evidence.hash_prev"] ?? "";
    if (i === 0) {
      // 第一条：hash_prev 为空则链起始正常
      result.set(i, hashPrev === "" ? null : false);
    } else {
      result.set(i, hashPrev === prevHash);
    }
    prevHash = rec["record_hash"] ?? "";
  }
  return result;
}

// ============================================================
// 统计
// ============================================================

function calcStats(records) {
  let total = records.length;
  let deny = 0;
  let warn = 0;
  const traces = new Set();
  for (const rec of records) {
    const d = inferDecision(rec);
    if (d === "DENY") deny++;
    if (d === "WARN") warn++;
    if (rec.trace_id) traces.add(rec.trace_id);
  }
  return { total, deny, warn, traces: traces.size };
}

// ============================================================
// DOM 渲染
// ============================================================

/**
 * 创建一个审计卡片 DOM 元素
 * @param {object} rec          - 审计记录
 * @param {number} seqDisplay   - 显示序号（倒序后的位置，从 1 起）
 * @param {boolean|null} chainOk - true=链正常, false=断链, null=首条/不验
 */
function createCard(rec, seqDisplay, chainOk) {
  const decision = inferDecision(rec);
  const toolName = rec["gen_ai.tool.name"] || rec.tool_name || "(未知工具)";
  const ts = formatTs(rec.timestamp || "");

  const card = document.createElement("div");
  card.className = "card";
  card.dataset.decision = decision;

  // --- 时间线圆点 ---
  const dot = document.createElement("div");
  dot.className = `card-dot ${decision}`;
  card.appendChild(dot);

  // --- 卡片头部 ---
  const header = document.createElement("div");
  header.className = "card-header";

  const seq = document.createElement("span");
  seq.className = "card-seq";
  seq.textContent = `#${seqDisplay}`;
  header.appendChild(seq);

  const tool = document.createElement("span");
  tool.className = "card-tool";
  tool.textContent = toolName;
  header.appendChild(tool);

  const badge = document.createElement("span");
  badge.className = `decision-badge ${decision}`;
  badge.textContent = DECISION_TEXT[decision] || decision;
  header.appendChild(badge);

  const tsSpan = document.createElement("span");
  tsSpan.className = "card-ts";
  tsSpan.textContent = ts;
  header.appendChild(tsSpan);

  const expandIcon = document.createElement("span");
  expandIcon.className = "expand-icon";
  expandIcon.textContent = "▶";
  header.appendChild(expandIcon);

  card.appendChild(header);

  // --- 卡片体（折叠） ---
  const body = document.createElement("div");
  body.className = "card-body";

  // 链状态行
  const chainRow = document.createElement("div");
  let chainClass = "chain-na-row";
  let chainIcon = "—";
  let chainText = "第一条记录，无前向哈希";
  if (chainOk === true) {
    chainClass = "chain-ok-row";
    chainIcon = "[OK]";
    chainText = "哈希链完整";
  } else if (chainOk === false) {
    chainClass = "chain-fail-row";
    chainIcon = "[FAIL]";
    chainText = "哈希链断裂 - hash_prev 与前一条 record_hash 不匹配";
  }
  chainRow.className = `chain-row ${chainClass}`;

  const ciEl = document.createElement("span");
  ciEl.className = "chain-icon";
  ciEl.textContent = chainIcon;
  chainRow.appendChild(ciEl);

  const chainDetails = document.createElement("span");
  chainDetails.innerHTML =
    `<span class="chain-hash-label">record_hash: </span>${shortHash(rec["record_hash"])}` +
    `&nbsp;&nbsp;` +
    `<span class="chain-hash-label">hash_prev: </span>${shortHash(rec["gen_ai.evidence.hash_prev"])}` +
    `&nbsp;&nbsp;` +
    chainText;
  chainRow.appendChild(chainDetails);
  body.appendChild(chainRow);

  // 规则命中 chips
  const policyHits = rec["gen_ai.policy.hit_id"] || [];
  const riskTags   = rec["gen_ai.classify.risk_tag"] || [];
  if (policyHits.length > 0 || riskTags.length > 0) {
    const chipsSection = document.createElement("div");
    chipsSection.style.marginBottom = "12px";

    if (policyHits.length > 0) {
      const label = document.createElement("div");
      label.className = "rule-chips-label";
      label.textContent = "命中规则";
      chipsSection.appendChild(label);
      const chips = document.createElement("div");
      chips.className = "rule-chips";
      for (const hit of policyHits) {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = hit;
        chips.appendChild(chip);
      }
      chipsSection.appendChild(chips);
    }

    if (riskTags.length > 0) {
      const label2 = document.createElement("div");
      label2.className = "rule-chips-label";
      label2.style.marginTop = policyHits.length > 0 ? "8px" : "0";
      label2.textContent = "风险标签";
      chipsSection.appendChild(label2);
      const chips2 = document.createElement("div");
      chips2.className = "rule-chips";
      for (const tag of riskTags) {
        const chip = document.createElement("span");
        chip.className = "chip risk-tag";
        chip.textContent = tag;
        chips2.appendChild(chip);
      }
      chipsSection.appendChild(chips2);
    }

    body.appendChild(chipsSection);
  }

  // 14 字段表格
  const table = document.createElement("table");
  table.className = "fields-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>字段</th><th>值</th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const key of ALL_FIELDS) {
    const val = rec[key];
    const valStr = formatValue(val);
    const tr = document.createElement("tr");
    const tdKey = document.createElement("td");
    tdKey.className = "field-key";
    tdKey.textContent = key;
    const tdVal = document.createElement("td");
    tdVal.className = valStr ? "field-val" : "field-val empty";
    tdVal.textContent = valStr || "(空)";
    tr.appendChild(tdKey);
    tr.appendChild(tdVal);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  body.appendChild(table);

  card.appendChild(body);

  // 展开/折叠点击
  header.addEventListener("click", () => {
    card.classList.toggle("expanded");
  });

  return card;
}

/**
 * 渲染时间线
 * @param {object[]} records - 原始顺序（时间升序）记录
 * @param {HTMLElement} container
 * @param {Map} chainMap - verifyChain 的结果
 */
function renderTimeline(records, container, chainMap) {
  container.innerHTML = "";

  if (records.length === 0) {
    container.innerHTML = `
      <div class="status-message">
        <div class="icon">[!]</div>
        <h3>文件中没有找到有效审计记录</h3>
        <p>请确认文件格式为每行一个 JSON 对象（JSONL 格式）。</p>
      </div>`;
    return;
  }

  // 按 timestamp 倒序
  const sorted = records.map((r, i) => ({ rec: r, origIdx: i }));
  sorted.sort((a, b) => {
    const ta = a.rec.timestamp || "";
    const tb = b.rec.timestamp || "";
    if (ta < tb) return 1;
    if (ta > tb) return -1;
    return 0;
  });

  const timeline = document.createElement("div");
  timeline.className = "timeline";

  for (let i = 0; i < sorted.length; i++) {
    const { rec, origIdx } = sorted[i];
    const chainOk = chainMap.has(origIdx) ? chainMap.get(origIdx) : null;
    const card = createCard(rec, i + 1, chainOk);
    timeline.appendChild(card);
  }

  container.appendChild(timeline);
}

/**
 * 更新统计条
 */
function updateStats(stats, chainMap, records) {
  document.getElementById("stat-total").textContent = stats.total;
  document.getElementById("stat-deny").textContent  = stats.deny;
  document.getElementById("stat-warn").textContent  = stats.warn;
  document.getElementById("stat-trace").textContent = stats.traces;

  // 链状态
  const failCount = [...chainMap.values()].filter(v => v === false).length;
  const chainBadge = document.getElementById("chain-global-badge");
  if (records.length === 0) {
    chainBadge.className = "chain-badge na";
    chainBadge.textContent = "无数据";
  } else if (failCount === 0) {
    chainBadge.className = "chain-badge ok";
    chainBadge.textContent = "哈希链完整";
  } else {
    chainBadge.className = "chain-badge fail";
    chainBadge.textContent = `${failCount} 条链断裂`;
  }
}

// ============================================================
// 数据加载
// ============================================================

/**
 * 读取文本并解析所有记录
 * @param {string} text
 * @returns {{records: object[], errors: string[]}}
 */
function parseJSONL(text) {
  const lines = text.split(/\r?\n/);
  const records = [];
  const errors = [];
  for (let i = 0; i < lines.length; i++) {
    const { record, error } = parseLine(lines[i]);
    if (error) errors.push(`行 ${i + 1}: ${error}`);
    if (record) records.push(record);
  }
  return { records, errors };
}

/**
 * 用 fetch + ReadableStream 逐行读取 JSONL（避免大文件一次性加载）
 * @param {string} url
 * @param {function(string): void} onLine - 每行回调
 * @returns {Promise<void>}
 */
async function fetchJSONLLines(url, onLine) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split(/\r?\n/);
    buf = parts.pop(); // 最后不完整行留给下一次
    for (const line of parts) {
      onLine(line);
    }
  }
  if (buf.trim()) onLine(buf);
}

// ============================================================
// 主控逻辑
// ============================================================

let currentRecords = [];

function processRecords(records) {
  currentRecords = records;
  const chainMap = verifyChain(records);
  const stats    = calcStats(records);
  const container = document.getElementById("timeline-container");
  renderTimeline(records, container, chainMap);
  updateStats(stats, chainMap, records);
}

function showLoading(msg) {
  const container = document.getElementById("timeline-container");
  container.innerHTML = `
    <div class="status-message">
      <div class="icon">[...]</div>
      <h3>${msg}</h3>
    </div>`;
}

function showError(msg) {
  const container = document.getElementById("timeline-container");
  container.innerHTML = `
    <div class="status-message">
      <div class="icon">[X]</div>
      <h3>加载失败</h3>
      <p>${msg}</p>
    </div>`;
}

/**
 * 从 URL 加载 JSONL
 */
async function loadFromURL(url) {
  showLoading("正在加载...");
  const records = [];
  try {
    await fetchJSONLLines(url, (line) => {
      const { record } = parseLine(line);
      if (record) records.push(record);
    });
    processRecords(records);
  } catch (err) {
    // fetch 失败（跨域、文件不存在等）提示用户拖拽或上传
    showError(`无法通过 fetch 加载文件（${err.message}）。<br>请使用下方"拖拽 / 选择文件"直接加载本地 .jsonl 文件。`);
  }
}

/**
 * 从 File 对象加载
 */
function loadFromFile(file) {
  showLoading(`正在读取 ${file.name}...`);
  const reader = new FileReader();
  reader.onload = (e) => {
    const { records, errors } = parseJSONL(e.target.result);
    processRecords(records);
    if (errors.length > 0) {
      console.warn("JSONL 解析警告:", errors);
    }
  };
  reader.onerror = () => showError("文件读取失败。");
  reader.readAsText(file, "utf-8");
}

// ============================================================
// DOM 事件绑定
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  // 加载路径输入 + 加载按钮
  const urlInput  = document.getElementById("audit-path");
  const loadBtn   = document.getElementById("btn-load-url");
  const sampleBtn = document.getElementById("btn-load-sample");
  const dropZone  = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");

  // 加载指定路径
  loadBtn.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (!url) return;
    loadFromURL(url);
  });

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadBtn.click();
  });

  // 加载示例数据
  sampleBtn.addEventListener("click", () => {
    loadFromURL("sample_audit.jsonl");
  });

  // 点击拖拽区触发文件选择
  dropZone.addEventListener("click", () => fileInput.click());

  // 文件选择
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) loadFromFile(file);
  });

  // 拖拽事件
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const file = e.dataTransfer?.files?.[0];
    if (file) loadFromFile(file);
  });

  // 页面拖拽放入
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (file && (file.name.endsWith(".jsonl") || file.name.endsWith(".json"))) {
      loadFromFile(file);
    }
  });

  // 初始：自动加载示例
  loadFromURL("sample_audit.jsonl");
});
