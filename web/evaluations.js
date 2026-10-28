(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { report: null, running: false, timer: null, loaded: false, revision: 0, comparisonOpen: false };
  const modes = { offline: "离线模板评测", live: "真实模型评测" };
  const categories = ["检索错误", "该追问没追问", "该转人工没转", "编造答案"];
  function element(tag, className = "", text = null) {
    const el = document.createElement(tag);
    el.className = className;
    if (text !== null) el.textContent = String(text);
    return el;
  }
  async function api(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const buyer = $("buyer-select").value === "buyer-b" ? "b" : "a";
      const response = await fetch(path, {
        method: body ? "POST" : "GET", cache: "no-store", signal: controller.signal,
        headers: { "X-Demo-Token": `local-buyer-${buyer}`, ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        throw new Error(response.status === 409 ? "评测正在运行，或真实模型未配置；请读取最近结果后检查模式。" : `评测服务暂不可用（HTTP ${response.status}）。已有结果仍保留。`);
      }
      return await response.json();
    } catch (error) {
      if (error.name === "AbortError") throw new Error("评测查询超时；任务可能仍在运行，请读取最近结果。");
      if (error instanceof TypeError) throw new Error("未能连接评测服务，已有结果仍保留。服务恢复后可读取最近结果。");
      throw error;
    } finally { clearTimeout(timer); }
  }
  function showError(error) {
    $("evaluation-error").textContent = error.message || "暂时无法连接评测服务，请检查本地服务后重试。";
    $("evaluation-error").hidden = false;
  }
  function busy(value) {
    state.running = value;
    $("evaluation-run").disabled = value;
    $("evaluation-button").disabled = value;
    $("evaluation-mode").disabled = value;
    $("evaluation-history").disabled = value;
    $("evaluation-run").textContent = value ? "正在运行…" : "重新运行 15 条";
  }
  function rawDetails(value) {
    const details = element("details", "eval-raw");
    details.append(element("summary", "", "查看完整响应与工具事件"), element("pre", "", JSON.stringify(value, null, 2)));
    return details;
  }
  function reportView(report) {
    const box = $("evaluation-results");
    box.replaceChildren();
    if (!report) {
      $("evaluation-status").textContent = "尚未运行 ＋";
      box.append(element("p", "eval-empty", "该模式尚无评测报告，点击运行会执行全部 15 条用例。"));
      return;
    }
    const active = ["queued", "running"].includes(report.status);
    $("evaluation-status").textContent = active ? `已完成 ${report.completed}/${report.total}` : `${report.passed}/${report.total} 通过 · ${modes[report.mode]}`;
    const overview = element("div", "eval-overview");
    const title = element("div");
    title.append(element("strong", "eval-score", active ? `${report.completed}/${report.total}` : `${report.passed}/${report.total}`), element("span", "", active ? " 实际执行进度" : ` 通过 · ${(report.pass_rate * 100).toFixed(0)}%`));
    const labels = { queued: "排队中", running: "执行中", completed: "已完成", failed: "运行中断" };
    title.append(element("p", "eval-note", `${modes[report.mode]} · ${labels[report.status]} · 有效执行 ${report.effective_executions} · 执行错误 ${report.execution_errors}`));
    if (report.mode === "live") title.append(element("p", "eval-note", `${report.model} · ${report.transport || "http"} · 已校验证据生成 ${report.verified_model_generations || 0} 次（其余用例由代码门控处理）`));
    overview.append(title);
    box.append(overview);
    if (report.matches_current_version === false) box.append(element("p", "eval-error", "这是其他代码或政策版本的历史报告，请重新运行后用于当前版本验收。"));
    if (report.error) box.append(element("p", "eval-error", report.error));
    const counts = element("div", "eval-counts");
    for (const [label, value] of Object.entries(report.category_results)) counts.append(element("span", "eval-count", `${label} ${value.passed}/${value.total}`));
    box.append(counts);
    const failures = element("div", "eval-failure-counts");
    for (const label of categories) failures.append(element("span", report.failure_counts[label] ? "has-failure" : "", `${label} ${report.failure_counts[label] || 0}`));
    box.append(failures);
    const metadata = element("details", "eval-provenance");
    metadata.append(element("summary", "", `本次记录 · ${report.started_at} · 查看版本与运行标识`), element("pre", "", JSON.stringify({run_id: report.run_id, started_at: report.started_at, finished_at: report.finished_at, mode: report.mode, model: report.model, transport: report.transport, verified_model_generations: report.verified_model_generations, demo_date: report.demo_date, policy_version: report.policy_version, fingerprints: report.fingerprints}, null, 2)));
    box.append(metadata);
    const list = element("div", "eval-cases");
    for (const result of report.results) {
      const row = element("details", `eval-case ${result.passed ? "passed" : "failed"}`);
      const summary = element("summary");
      summary.append(element("span", "eval-case-id", result.id), element("span", "eval-result", result.passed ? "✓ 通过" : "✕ 未通过"), element("span", "eval-case-input", result.input), element("span", "eval-case-category", result.category));
      row.append(summary);
      const content = element("div", "eval-case-body");
      for (const [label, text] of [["通过判据", result.expected], ["实际回复", result.summary], ["失败分类", result.failure_categories.join(" / ") || (result.execution_error ? "execution_error · 执行错误" : "—")], ["修复动作", result.fix_action]]) {
        const p = element("p"); p.append(element("strong", "", label + "："), document.createTextNode(text)); content.append(p);
      }
      const actual = result.actual;
      if (result.execution_error && actual) {
        const generation = actual.trace_events.find(event => event.step === "generation" && event.status === "error");
        const code = generation?.data?.provider_code;
        const labels = {"1305":"模型当前繁忙", "1302":"请求速率受限", "1113":"账户配额或余额受限", "1315":"密钥产品类型不匹配"};
        const issue = labels[code] || generation?.data?.error_code || result.execution_error;
        content.append(element("p", "has-failure", `执行错误：${issue}${code ? `（${code}）` : ""}。该条未通过，不计入四类业务错误。`));
      }
      if (actual) content.append(element("p", "", `动作：${actual.action} · 引用：${actual.policy_ids.join(" / ") || "无"} · 规则：${actual.triggered_rules.join(" / ") || "无"} · top1：${actual.retrieval_score === null ? "未执行检索" : actual.retrieval_score.toFixed(3)} · 工单：${result.verified_ticket ? "已通过接口查验" : "无"}`));
      const checks = element("ul", "eval-checks");
      for (const check of result.checks) checks.append(element("li", check.passed ? "" : "has-failure", `${check.passed ? "✓" : "✕"} ${check.name}`));
      content.append(checks, rawDetails({actual: result.actual, verified_ticket: result.verified_ticket}));
      row.append(content); list.append(row);
    }
    box.append(list);
  }
  function runLabel(report) {
    const time = new Date(report.started_at).toLocaleString("zh-CN", {hour12:false, timeZone:"Asia/Shanghai"});
    const failed = report.failed_cases.length ? ` · 未通过 ${report.failed_cases.join("、")}` : "";
    return `${time} · ${report.model || modes[report.mode]} · ${report.passed}/${report.total}${failed}`;
  }
  function comparisonView(comparison) {
    const box = $("evaluation-comparison");
    const wasOpen = state.comparisonOpen;
    box.replaceChildren();
    const selectedId = state.report?.run_id;
    if (!comparison || ![comparison.before.run_id, comparison.after.run_id].includes(selectedId)) {
      if (state.report?.mode === "live") box.append(element("p", "eval-note", "本轮暂无已记录的修复对比。"));
      return;
    }
    const row = element("details", "failure-record");
    row.open = wasOpen;
    row.addEventListener("toggle", () => { if (row.isConnected) state.comparisonOpen = row.open; });
    row.append(element("summary", "", "ERNIE · E02 超时 → 调整预算后复测通过 · 查看对比"));
    const body = element("div", "failure-record-body");
    body.append(element("p", "eval-note", "真实历史记录 · 独立于当前成绩 · 输入：ORD-1001 能退吗？"));
    const columns = element("div", "failure-comparison");
    for (const [label, side] of [["修复前", comparison.before], ["调整后复测", comparison.after]]) {
      const selected = side.run_id === selectedId;
      const card = element("div", selected ? "comparison-selected" : "");
      card.append(element("h4", "", `${label} · ${side.passed}/${side.total}${selected ? " · 当前查看" : ""}`),
        element("p", side.case.passed ? "" : "has-failure", `E02 ${side.case.passed ? "通过" : "未通过 · 执行错误"}`),
        element("p", "", side.case.summary));
      const error = side.case.actual?.trace_events.find(e => e.step === "generation" && e.status === "error");
      if (error) card.append(element("p", "has-failure", `记录错误：${error.data.error_code} · ${(error.duration_ms / 1000).toFixed(1)} 秒（含重试）`));
      const button = element("button", "button outline", "查看该轮全部用例");
      button.type = "button";
      button.addEventListener("click", () => { if (!state.running) historical(side.run_id); });
      card.append(button); columns.append(card);
    }
    body.append(columns,
      element("p", "", "定位：原单次 15 秒请求预算内未取得有效响应；代码安全追问，没有承诺退款。"),
      element("p", "", "修复：ERNIE 单次请求预算调整为 30 秒，外层 35 秒，最多两次发送；金额和置信度规则保持不变。"),
      element("p", "eval-note", "调整后该轮复测通过；单轮结果不能证明长期稳定性。原始响应、事件与判据可在对应记录中展开查看。"));
    row.append(body); box.append(row);
  }
  async function loadHistory(revision) {
    try {
      const data = await api(`/api/evaluations/history?mode=${$("evaluation-mode").value}`);
      if (revision !== state.revision) return;
      const select = $("evaluation-history");
      select.replaceChildren(element("option", "", "选择一轮历史记录…"));
      select.firstElementChild.value = "";
      for (const report of data.reports) {
        const option = element("option", "", runLabel(report));
        option.value = report.run_id; select.append(option);
      }
      if (state.report) select.value = state.report.run_id;
      $("history-note").textContent = `共 ${data.reports.length} 轮记录 · 当前模式下所有模型 · 查看不会重新调用模型。历史成绩仅代表当时版本。`;
      comparisonView(data.comparison);
    } catch (error) {
      if (revision !== state.revision) return;
      $("history-note").textContent = "历史列表读取失败；已有结果保留，可点击读取最近结果重试。";
      showError(error);
    }
  }
  async function historical(runId) {
    const revision = ++state.revision;
    clearTimeout(state.timer);
    $("evaluation-error").hidden = true;
    $("evaluation-comparison").replaceChildren();
    await poll(runId, revision);
    if (revision === state.revision) $("evaluation-history").value = runId;
  }
  async function poll(runId, revision) {
    clearTimeout(state.timer);
    try {
      const report = await api(`/api/evaluations/${encodeURIComponent(runId)}`);
      if (revision !== state.revision) return;
      state.report = report;
      reportView(report);
      const active = ["queued", "running"].includes(report.status);
      busy(active);
      if (active) state.timer = setTimeout(() => poll(runId, revision), 1000);
      else await loadHistory(revision);
    } catch (error) {
      if (revision !== state.revision) return;
      busy(false); showError(error);
    }
  }
  async function latest() {
    const revision = ++state.revision;
    clearTimeout(state.timer);
    $("evaluation-error").hidden = true;
    try {
      const data = await api(`/api/evaluations/latest?mode=${$("evaluation-mode").value}`);
      if (revision !== state.revision) return;
      state.report = data.report;
      reportView(data.report);
      const active = data.report && ["queued", "running"].includes(data.report.status);
      busy(Boolean(active));
      if (active) state.timer = setTimeout(() => poll(data.report.run_id, revision), 1000);
      await loadHistory(revision);
    } catch (error) { if (revision === state.revision) { busy(false); showError(error); } }
  }
  async function run() {
    if (state.running) return;
    state.loaded = true;
    $("evaluation-panel").open = true;
    $("evaluation-panel").scrollIntoView({block:"start", behavior:"smooth"});
    $("evaluation-error").hidden = true;
    busy(true);
    const revision = ++state.revision;
    clearTimeout(state.timer);
    try {
      const response = await api("/api/evaluations", {mode: $("evaluation-mode").value});
      if (revision === state.revision) await poll(response.run_id, revision);
    } catch (error) { if (revision === state.revision) { busy(false); showError(error); } }
    loadFailures();
  }
  async function loadFailures() {
    if ($("evaluation-mode").value !== "offline") return;
    const revision = state.revision;
    try {
      const data = await api("/api/failure-cases");
      if (revision !== state.revision || $("evaluation-mode").value !== "offline") return;
      const box = $("failure-cases"); box.replaceChildren();
      if (!data.cases.length) box.append(element("p", "eval-empty", "尚未记录真实失败样本。"));
      for (const item of data.cases) {
        const record = item.record;
        const amountCase = record.id === "F-MONEY-001";
        const row = element("details", "failure-record");
        row.append(element("summary", "", amountCase ? "F-MONEY-001 · “一些钱”被误识别为 1 元 · 查看修复前后" : `${record.id} · 退款时间检索召回不足 · 查看修复前后`));
        const body = element("div", "failure-record-body");
        body.append(element("p", "eval-note", `证据来源：${item.source_file} · 历史开发样本，非 E08 失败记录。`));
        if (amountCase) {
          const comparison = element("div", "failure-comparison");
          for (const [label, turns] of [["修复前 · 真实记录", record.before], ["修复后 · 同输入回放", record.after]]) {
            const side = element("div"); side.append(element("h4", "", label));
            for (const turn of turns) side.append(element("p", "failure-input", turn.input), element("p", "", turn.output.message));
            comparison.append(side);
          }
          body.append(comparison, element("p", "", `根因：${record.root_cause}`), element("p", "", `修复：${typeof record.fix === "string" ? record.fix : JSON.stringify(record.fix)}`));
        } else {
          body.append(element("p", "", "输入：退款多久到账？（旧记录部分说明存在编码损失，保留原始证据）"), element("p", "", `修复前：${record.before.action}，top1=${record.before.retrieval_score.toFixed(3)}；修复后：${record.after.action}，top1=${record.after.retrieval_score.toFixed(3)}，引用 ${record.after.policy_ids.join(" / ")}。`), element("p", "", "保留 0.6 门槛，调整逐条检索表示并补充退款时间问法；未把低分强制改成通过。"));
        }
        body.append(rawDetails(record)); row.append(body); box.append(row);
      }
    } catch (error) { if (revision !== state.revision || $("evaluation-mode").value !== "offline") return; $("failure-cases").replaceChildren(element("p", "eval-error", "真实失败记录暂时无法读取，未展示预置复盘。")); }
  }
  $("evaluation-button").addEventListener("click", run);
  $("evaluation-run").addEventListener("click", run);
  $("evaluation-refresh").addEventListener("click", latest);
  $("evaluation-mode").addEventListener("change", () => {
    $("evaluation-history").replaceChildren();
    $("evaluation-comparison").replaceChildren();
    $("offline-failures").hidden = $("evaluation-mode").value !== "offline";
    latest().then(loadFailures);
  });
  $("evaluation-history").addEventListener("change", event => {
    if (event.target.value) historical(event.target.value);
  });
  $("evaluation-panel").addEventListener("toggle", () => {
    if ($("evaluation-panel").open && !state.loaded) { state.loaded = true; latest(); loadFailures(); }
  });
  api("/api/demo").then((meta) => {
    if (meta.live_evaluation_available) {
      const option = $("evaluation-mode").querySelector('[value="live"]');
      option.disabled = false; option.textContent = "真实模型 · 独立验收";
    }
  }).catch(() => {});
})();
