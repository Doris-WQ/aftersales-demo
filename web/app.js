"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const TOKENS = { "buyer-a": "local-buyer-a", "buyer-b": "local-buyer-b" };
  const ACTIONS = { answer: "政策回答", query_result: "订单查询", clarify: "追问", handoff: "转人工", refuse: "拒绝查询" };
  const INTENTS = { policy: "政策问答", order_query: "订单查询", return: "售后退款", unknown: "待进一步明确" };
  const REASONS = { amount_limit: "金额超过阈值", complaint: "投诉事项", human_requested: "用户请求人工", low_confidence: "检索证据不足", evidence_answer: "依据政策回答", missing_order_id: "缺订单号", missing_reason: "缺退货原因", missing_evidence: "缺图片凭证", missing_condition: "缺商品状态", quality_review: "质量与凭证待核验", policy_out_of_range: "超出自动判断范围", order_not_found: "未查到授权订单", order_unavailable: "订单暂不可查询", generation_failed: "回答未通过验证", policy_source_mismatch: "适用政策不匹配", expired_order: "签收已超七天", order_found: "已查询授权订单", other_order: "禁止查询他人订单", multiple_orders: "需要明确单个订单", invalid_requested_amount: "退款金额待明确" };
  const state = { buyer: "buyer-b", session: null, turns: [], selected: null, busy: false, connected: false, metadata: null, epoch: 0, controllers: new Set(), sequence: 0, composing: false };

  function node(tag, className = "", text = null) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== null) element.textContent = String(text);
    return element;
  }
  const money = (amount) => Number.isFinite(Number(amount)) ? new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(Number(amount)) : "未知";
  const cents = (amount) => amount === null || amount === undefined ? "未提供" : money(Number(amount) / 100);
  const scoreText = (score) => Number.isFinite(score) ? score.toFixed(3) : "—";
  const reasonText = (reason) => REASONS[reason] || reason;
  // Keep source IDs in the response and evidence panels, not in the customer-facing reply.
  const chatText = (text) => String(text).replace(/\[\s*p\d{2}\s*\][\t ]*/gi, "").trim();
  const selectedTurn = () => state.turns.find((turn) => turn.id === state.selected);
  const announce = (text) => { $("announcement").textContent = text; };

  async function request(path, { method = "GET", body = undefined, epoch = state.epoch, token = TOKENS[state.buyer] } = {}) {
    const controller = new AbortController();
    state.controllers.add(controller);
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 45000);
    try {
      const response = await fetch(path, { method, signal: controller.signal, cache: "no-store", headers: { "X-Demo-Token": token, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
      if (epoch !== state.epoch) throw new DOMException("会话已切换", "AbortError");
      if (!response.ok) {
        const error = new Error(response.status === 409 ? "这个入口已过期，请使用最新一轮消息的转人工入口。" : response.status === 404 ? "会话或记录已失效，请重置对话后重试。" : response.status === 401 ? "演示身份未通过校验，请重新选择身份。" : `服务暂不可用（HTTP ${response.status}），未自动重试。`);
        error.status = response.status;
        throw error;
      }
      return await response.json();
    } catch (error) {
      if (timedOut) throw new Error("服务响应超时，未自动重试。请检查服务后再操作。");
      if (error.name === "AbortError" || error.status) throw error;
      throw new Error("未能连接服务，尚未收到本轮结果。请检查服务后再试。");
    } finally {
      clearTimeout(timer);
      state.controllers.delete(controller);
    }
  }

  function setConnection(status, message) {
    const indicator = $("connection-status");
    indicator.className = `connection ${status}`;
    indicator.replaceChildren(node("i"), document.createTextNode(message));
  }

  function controls() {
    $("message-input").disabled = !state.connected || state.busy;
    $("send-button").disabled = !state.connected || state.busy || !$("message-input").value.trim();
    $("send-button").replaceChildren(document.createTextNode(state.busy ? "处理中" : "发送"), node("span", "", "↗"));
    for (const button of document.querySelectorAll(".quick-chip, .sample-order")) button.disabled = !state.connected || state.busy;
    $("composer-hint").textContent = state.busy ? "正在等待实际执行结果…" : "Enter 发送 · Shift + Enter 换行";
  }

  function showServiceProblem(error) {
    state.connected = false;
    setConnection("failed", "服务暂不可用");
    const alert = $("global-error");
    alert.hidden = false;
    alert.replaceChildren(document.createTextNode(error.message));
    const retry = node("button", "reconnect", "重新连接");
    retry.type = "button";
    retry.onclick = () => loadMetadata(state.epoch);
    alert.append(retry);
  }

  async function loadMetadata(epoch) {
    state.connected = false;
    setConnection("", "连接服务中");
    controls();
    try {
      const meta = await request("/api/demo", { epoch });
      if (epoch !== state.epoch) return;
      if (meta.buyer !== state.buyer || !Array.isArray(meta.orders) || !["offline", "live"].includes(meta.mode)) throw new Error("服务返回的演示配置不一致，请检查服务。");
      state.metadata = meta;
      state.connected = true;
      $("global-error").hidden = true;
      setConnection("connected", "服务已连接");
      $("mode-badge").textContent = meta.mode === "offline" ? "离线模板模式" : "真实模型模式";
      $("mode-badge").classList.toggle("is-live", meta.mode === "live");
      renderQuickActions();
      renderChat(false);
    } catch (error) {
      if (epoch !== state.epoch || error.name === "AbortError") return;
      showServiceProblem(error);
      announce(error.message);
    } finally {
      if (epoch === state.epoch) controls();
    }
  }

  function renderQuickActions() {
    const box = $("quick-actions");
    box.replaceChildren();
    const orderId = state.metadata?.orders[0]?.order_id;
    const examples = [["政策问答", "七天无理由从哪天算？"], ["信息追问", "我想退货"], ...(orderId ? [["订单退款", `${orderId} 我要退款`]] : []), ["投诉转人工", "你们再这样我投诉"]];
    for (const [label, message] of examples) {
      const button = node("button", "quick-chip", label);
      button.type = "button";
      button.title = message;
      button.onclick = () => submit(message);
      box.append(button);
    }
  }

  function robotAvatar(className = "agent-symbol") {
    const avatar = node("span", className);
    avatar.setAttribute("aria-hidden", "true");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    for (const [tag, attributes] of [
      ["rect", { x: 4, y: 7, width: 16, height: 13, rx: 4, fill: "none", stroke: "currentColor", "stroke-width": 1.7 }],
      ["path", { d: "M12 3v4M2 11v5M22 11v5M9 16h6", fill: "none", stroke: "currentColor", "stroke-width": 1.7, "stroke-linecap": "round" }],
      ["circle", { cx: 8.5, cy: 12, r: 1.3, fill: "currentColor" }],
      ["circle", { cx: 15.5, cy: 12, r: 1.3, fill: "currentColor" }],
    ]) {
      const shape = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [name, value] of Object.entries(attributes)) shape.setAttribute(name, String(value));
      svg.append(shape);
    }
    avatar.append(svg);
    return avatar;
  }

  function welcome() {
    const box = node("div", "welcome");
    const introduction = node("p", "", "问一条退货政策，或给我一个订单号。");
    introduction.append(node("br"), document.createTextNode("判断依据会同步出现在右边。"));
    box.append(robotAvatar("welcome-emblem"), node("h3", "", "你好，请问有什么能够帮您^.^"), introduction);
    box.append(node("div", "sample-label", "当前身份的模拟订单 · 点击查询"));
    const orders = node("div", "sample-orders");
    for (const order of state.metadata?.orders || []) {
      const button = node("button", "sample-order");
      button.type = "button";
      button.append(node("strong", "", order.order_id), node("span", "", `${order.item} · ${money(order.amount)}`));
      button.onclick = () => submit(`查 ${order.order_id} 的订单状态`);
      orders.append(button);
    }
    if (!orders.childNodes.length) orders.append(node("span", "sample-label", "正在读取当前身份的订单…"));
    box.append(orders);
    return box;
  }

  function ticketCard(turn) {
    const ticket = turn.manualResult?.ticket || turn.ticket;
    const ticketId = ticket?.handoff_id || turn.response?.handoff_id;
    if (!ticketId) return null;
    const box = node("div", "handoff-card");
    box.setAttribute("data-testid", "ticket-card");
    const reason = ticket?.reason_code || turn.response?.reason_code;
    const description = reason === "amount_limit" ? "单笔退款金额超过阈值，待人工核实。"
      : reason === "complaint" ? "投诉事项已转人工，待人工核实。"
      : reason === "quality_review" ? "质量问题与图片凭证，待人工核实。"
      : "当前事项已转人工，待人工核实。";
    const titleRow = node("div", "handoff-title-row");
    titleRow.append(node("h3", "ticket-id", ticketId), node("span", "ticket-kind", "模拟工单"));
    box.append(titleRow, node("p", "ticket-description", description));
    if (turn.ticketError) box.append(node("p", "handoff-error", turn.ticketError));
    return box;
  }

  function renderChat(scrollLatest) {
    const log = $("conversation");
    const previousScroll = log.scrollTop;
    const wasAtBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 12;
    log.replaceChildren();
    if (!state.turns.length) log.append(welcome());
    for (const [index, turn] of state.turns.entries()) {
      const row = node("article", `turn${turn.id === state.selected ? " selected" : ""}`);
      row.classList.toggle("is-handoff", turn.response?.action === "handoff" || Boolean(turn.manualResult));
      row.dataset.turnId = turn.id;
      const userLine = node("div", "user-line");
      userLine.append(node("div", "user-bubble", turn.input));
      const label = node("div", "agent-label");
      label.append(robotAvatar(), document.createTextNode("售后小巾"));
      const answer = node("div", "answer-box");
      if (turn.response) {
        const response = turn.response;
        answer.append(node("div", "agent-message", chatText(response.message)));
        const meta = node("div", "turn-meta");
        meta.append(node("span", `action-pill ${turn.manualResult ? "handoff" : response.action}`, turn.manualResult ? "追问后已转人工" : ACTIONS[response.action]));
        const inspect = node("button", "turn-link", turn.id === state.selected ? "正在查看本轮 ↗" : "查看本轮轨迹 ↗");
        inspect.type = "button";
        inspect.setAttribute("aria-label", `查看第${index + 1}轮轨迹`);
        inspect.setAttribute("aria-pressed", String(turn.id === state.selected));
        inspect.onclick = () => { state.selected = turn.id; renderChat(turn === state.turns.at(-1)); renderEvidence(); };
        meta.append(inspect);
        answer.append(meta);
        const card = ticketCard(turn);
        if (card) answer.append(card);
        if (response.handoff_available && !turn.manualResult) {
          const latest = turn === state.turns.at(-1);
          const manualButton = node("button", "manual-button", turn.manualBusy ? "正在创建模拟工单…" : latest ? "转人工核实 ↗" : "历史入口已失效");
          manualButton.type = "button";
          manualButton.disabled = state.busy || !latest || !state.connected;
          manualButton.onclick = () => createManualTicket(turn);
          answer.append(manualButton);
        }
        if (turn.manualError) answer.append(node("p", "handoff-error", turn.manualError));
      } else if (turn.error) {
        answer.append(node("div", "error-message", turn.error));
      } else {
        const pending = node("div", "pending-text");
        pending.append(node("span", "spinner"), document.createTextNode("正在处理你的问题…"));
        answer.append(pending);
      }
      row.append(userLine, label, answer);
      log.append(row);
    }
    controls();
    if (scrollLatest || (wasAtBottom && state.selected === state.turns.at(-1)?.id)) log.scrollTop = log.scrollHeight;
    else log.scrollTop = previousScroll;
  }

  function emptyState(title, description, symbol = "⌁") {
    const empty = node("div", "empty-state");
    empty.append(node("span", "empty-symbol", symbol), node("h3", "", title), node("p", "", description));
    return empty;
  }

  const traceRenderCache = new WeakMap();

  function buildTraceTurn(turn) {
    const box = node("div", "trace-turn-content");
    if (!turn || !turn.response) {
      const empty = emptyState(turn ? turn.error ? "尚未收到执行记录" : "正在等待本轮记录" : "每一次判断，都看得见", turn ? turn.error ? "连接失败时不推测规则或订单状态。" : "服务端返回后展示实际结论。" : "从左侧发出一个问题，这里会展示判断的逻辑主干。");
      if (turn && !turn.error) empty.prepend(node("span", "spinner"));
      box.append(empty);
      return box;
    }
    const response = turn.response;
    const events = [...response.trace_events, ...(turn.manualResult?.trace_events || [])];
    const rules = [...new Set(events.filter(event => event.step === "rule").map(event => event.data.rule_id).filter(Boolean))];
    const intent = events.find(event => event.step === "intent")?.data;
    const amount = events.find(event => event.step === "amount_check")?.data
      || events.find(event => event.step === "rule" && event.data.rule_id === "R1")?.data;
    const ticketEvent = [...events].reverse().find(event => event.step === "handoff");
    const hasTicket = Boolean(turn.manualResult?.ticket || response.handoff_id);
    const action = turn.manualResult ? "handoff" : response.action;
    const summary = node("div", "decision-summary");
    const main = node("div", "decision-main");
    main.append(node("strong", "", turn.manualResult ? "追问后已转人工" : ACTIONS[action]));
    summary.append(node("div", "decision-title", "本轮结论"), main);
    box.append(summary);

    const conclusions = node("dl", "logic-mainline");
    const add = (label, value) => {
      const row = node("div", "logic-row");
      row.append(node("dt", "logic-label", label), node("dd", "logic-value", value));
      conclusions.append(row);
    };
    if (intent) {
      const resolvedIntent = rules.includes("R3")
        ? response.reason_code === "complaint" ? "投诉" : "人工请求"
        : intent.kind === "return" ? "退款" : INTENTS[intent.kind] || "待明确";
      add("意图", resolvedIntent);
    }
    if (intent?.order_id) add("提取订单号", intent.order_id);
    else if (response.order) add("关联订单号", response.order.order_id);
    if (action === "query_result") add("订单查询", response.order?.status || "已查到授权订单");
    if (response.reason_code === "order_not_found") add("订单查询", "未查到可访问订单");
    if (response.reason_code === "order_unavailable") add("订单查询", "暂时无法查询");
    if (amount && Number.isFinite(amount.gate_amount_cents) && Number.isFinite(amount.limit_cents)) {
      const displayAmount = value => new Intl.NumberFormat("zh-CN", { useGrouping: false, maximumFractionDigits: 2 }).format(value / 100);
      const comparison = amount.gate_amount_cents > amount.limit_cents ? ">" : amount.gate_amount_cents === amount.limit_cents ? "=" : "<";
      add("金额检查", `${displayAmount(amount.gate_amount_cents)} ${comparison} ${displayAmount(amount.limit_cents)}`);
    }
    if (response.missing_fields.length) {
      const fields = { order_id: "订单号", reason: "退货原因", amount: "退款金额", condition: "商品状态", evidence: "图片凭证", question: "具体问题" };
      add("待补信息", response.missing_fields.map(field => fields[field] || field).join("、"));
    }
    if (rules.length) add("规则", rules.map(rule => `${rule} 触发`).join(" · "));
    if (rules.includes("R2")) add("检索结论", "依据不足，只追问");
    if (response.policy_ids.length) {
      const direct = events.some(event => event.step === "retrieval" && event.data.source === "code_rule");
      add("政策依据", `${response.policy_ids.join(" / ")} · ${direct ? "规则引用" : "检索引用"}`);
    }
    add("最终动作", hasTicket ? `转人工 · ${ticketEvent?.data.reused ? "已复用模拟工单" : "已创建模拟工单"}` : ACTIONS[action]);
    box.append(conclusions);

    const raw = node("details", "trace-raw");
    const toggle = node("summary", "", "[+] 查看原始数据");
    raw.append(toggle, node("pre", "", JSON.stringify({ chat_response: response, ...(turn.manualResult ? { manual_handoff: turn.manualResult } : {}) }, null, 2)));
    raw.addEventListener("toggle", () => { toggle.textContent = raw.open ? "[-] 收起原始数据" : "[+] 查看原始数据"; });
    box.append(raw);
    return box;
  }

  function renderTrace() {
    const container = $("trace-content");
    if (!state.turns.length) {
      container.replaceChildren(buildTraceTurn(null));
      return;
    }
    const followLatest = container.scrollTop + container.clientHeight >= container.scrollHeight - 24;
    let timeline = container.querySelector(".decision-timeline");
    if (!timeline) {
      timeline = node("ol", "decision-timeline");
      timeline.setAttribute("aria-label", "按对话轮次追加的决策轨迹");
      container.replaceChildren(timeline);
    }
    let changed = false;
    for (const [index, turn] of state.turns.entries()) {
      let cached = traceRenderCache.get(turn);
      if (!cached || cached.element.parentNode !== timeline) {
        const element = node("li", "trace-turn");
        element.dataset.traceTurnId = turn.id;
        const header = node("div", "trace-turn-header");
        const question = node("span", "trace-turn-question", turn.input.length > 60 ? `${turn.input.slice(0, 60)}…` : turn.input);
        question.title = turn.input;
        header.append(node("span", "trace-round", `第 ${index + 1} 轮`), question);
        element.append(header, buildTraceTurn(turn));
        timeline.append(element);
        cached = { element, response: turn.response, manualResult: turn.manualResult, error: turn.error };
        traceRenderCache.set(turn, cached);
        changed = true;
      } else if (cached.response !== turn.response || cached.manualResult !== turn.manualResult || cached.error !== turn.error) {
        const previous = cached.element.querySelector(".trace-turn-content");
        const wasOpen = Boolean(previous.querySelector(".trace-raw")?.open);
        const content = buildTraceTurn(turn);
        const raw = content.querySelector(".trace-raw");
        if (raw && wasOpen) {
          raw.open = true;
          raw.querySelector("summary").textContent = "[-] 收起原始数据";
        }
        previous.replaceWith(content);
        cached.response = turn.response;
        cached.manualResult = turn.manualResult;
        cached.error = turn.error;
        changed = true;
      }
      cached.element.classList.toggle("selected", turn.id === state.selected);
    }
    if (changed && followLatest) container.scrollTop = container.scrollHeight;
  }
  function sectionLabel(title, badge) {
    const label = node("div", "section-label", title);
    if (badge) label.append(node("span", "source-tag", badge));
    return label;
  }

  function orderCard(order) {
    const card = node("div", "order-card");
    card.setAttribute("data-testid", "order-card");
    const heading = node("div", "order-top");
    heading.append(node("span", "order-id", order.order_id), node("span", "status-badge", order.status));
    const amount = node("div", "order-amount", money(order.amount));
    amount.append(node("small", "", "商品实付"));
    card.append(heading, node("h3", "order-title", order.item), amount);
    const details = node("dl", "order-facts");
    for (const [label, value] of [["品类", order.category], ["签收日期", order.signed_date || "未签收"], ["吊牌状态", order.tags_intact === null ? "未知" : order.tags_intact ? "完好" : "不完好"], ["二次销售", order.resale_condition_ok === null ? "未知" : order.resale_condition_ok ? "不受影响" : "受影响"], ["图片凭证", order.evidence_status === "uploaded_unverified" ? "已上传 · 待核验" : "未上传"]]) {
      const row = node("div");
      row.append(node("dt", "", label), node("dd", "", value));
      details.append(row);
    }
    card.append(details);
    return card;
  }

  function renderContext(turn) {
    const box = $("context-content");
    box.replaceChildren();
    const response = turn?.response;
    const orderSection = node("div", "context-section");
    orderSection.append(sectionLabel("关联订单", response?.order ? "当前身份" : null));
    if (response?.order) orderSection.append(orderCard(response.order));
    else {
      const empty = node("div", "no-context");
      empty.append(node("strong", "", turn?.error ? "未收到订单结果" : "本轮暂无关联订单"), node("p", "", "仅展示服务端授权返回的订单事实"));
      orderSection.append(empty);
    }
    const policySection = node("div", "context-section");
    const fromRule = response?.trace_events.some((event) => event.step === "retrieval" && event.data.source === "code_rule");
    policySection.append(sectionLabel("政策依据", response?.policy_cards.length ? fromRule ? "规则直接引用" : "检索引用" : null));
    for (const policy of response?.policy_cards || []) {
      const card = node("article", "policy-card");
      card.setAttribute("data-policy-id", policy.id);
      const heading = node("h3", "policy-heading");
      heading.append(node("span", "policy-id", policy.id), document.createTextNode(policy.title));
      card.append(heading, node("p", "", policy.content), node("p", "policy-applicability", `适用：${policy.applicability} · ${policy.version}`));
      policySection.append(card);
    }
    if (!response?.policy_cards.length) {
      const empty = node("div", "no-context");
      empty.append(node("strong", "", "暂无可引用政策"), node("p", "", response?.reason_code === "low_confidence" ? "证据不足，本轮不输出政策细节" : "回答时同步展示引用的政策条目"));
      policySection.append(empty);
    }
    box.append(orderSection, policySection);
  }

  function renderEvidence() {
    const turn = selectedTurn();
    renderTrace();
    renderContext(turn);
    if (renderEvidence.lastTurnId !== turn?.id) {
      const container = $("trace-content");
      const entry = turn ? traceRenderCache.get(turn)?.element : null;
      container.scrollTop = entry
        ? Math.max(0, entry.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 8)
        : 0;
      $("context-content").scrollTop = 0;
      renderEvidence.lastTurnId = turn?.id;
    }
  }

  async function loadTicket(turn, epoch, token) {
    turn.ticketLoading = true;
    renderChat(false);
    try {
      const ticket = await request(`/api/handoffs/${encodeURIComponent(turn.response.handoff_id)}?session_id=${encodeURIComponent(turn.response.session_id)}`, { epoch, token });
      if (epoch !== state.epoch) return;
      turn.ticket = ticket;
    } catch (error) {
      if (epoch !== state.epoch || error.name === "AbortError") return;
      turn.ticketError = "服务端已返回工单编号，但详情暂时无法读取。";
    } finally {
      if (epoch === state.epoch) { turn.ticketLoading = false; renderChat(false); }
    }
  }

  async function submit(text) {
    if (state.busy || !state.connected || !text.trim()) return;
    const input = text.trim();
    if (input.length > 2000) { announce("问题不能超过 2000 个字符。"); return; }
    const epoch = state.epoch;
    const token = TOKENS[state.buyer];
    const turn = { id: `turn-${++state.sequence}`, input, response: null };
    state.turns.push(turn);
    state.selected = turn.id;
    state.busy = true;
    $("message-input").value = "";
    renderChat(true);
    renderEvidence();
    try {
      const response = await request("/api/chat", { method: "POST", body: { session_id: state.session, message: input }, epoch, token });
      if (epoch !== state.epoch) return;
      turn.response = response;
      state.session = response.session_id;
      announce(`${ACTIONS[response.action]}：${chatText(response.message)}`);
    } catch (error) {
      if (epoch !== state.epoch || error.name === "AbortError") return;
      turn.error = error.message;
      if (!error.status || error.status >= 500) showServiceProblem(error);
      if (error.status === 404) state.session = null;
      announce(error.message);
    } finally {
      if (epoch === state.epoch) { state.busy = false; renderChat(true); renderEvidence(); $("message-input").focus(); }
    }
    if (turn.response?.handoff_id && epoch === state.epoch) loadTicket(turn, epoch, token);
  }

  async function createManualTicket(turn) {
    if (state.busy || !state.connected || turn !== state.turns.at(-1) || turn.manualResult) return;
    const epoch = state.epoch;
    state.busy = true;
    turn.manualBusy = true;
    turn.manualError = null;
    renderChat(false);
    try {
      const result = await request("/api/handoffs", { method: "POST", body: { session_id: turn.response.session_id, trace_id: turn.response.trace_id }, epoch });
      if (epoch !== state.epoch) return;
      turn.manualResult = result;
      announce(`已创建模拟转人工工单 ${result.ticket.handoff_id}`);
    } catch (error) {
      if (epoch !== state.epoch || error.name === "AbortError") return;
      turn.manualError = error.message;
      if (!error.status || error.status >= 500) showServiceProblem(error);
      announce(error.message);
    } finally {
      if (epoch === state.epoch) { state.busy = false; turn.manualBusy = false; renderChat(true); renderEvidence(); }
    }
  }

  function reset(buyer = state.buyer) {
    state.epoch += 1;
    for (const controller of state.controllers) controller.abort();
    state.controllers.clear();
    state.buyer = buyer;
    state.session = null;
    state.turns = [];
    state.selected = null;
    state.busy = false;
    state.connected = false;
    state.metadata = null;
    $("message-input").value = "";
    $("mode-badge").textContent = "等待服务";
    $("mode-badge").classList.remove("is-live");
    $("quick-actions").replaceChildren();
    $("global-error").hidden = true;
    renderChat(false);
    renderEvidence();
    announce("已重置对话，使用新会话。");
    loadMetadata(state.epoch);
  }

  $("chat-form").addEventListener("submit", (event) => { event.preventDefault(); submit($("message-input").value); });
  $("message-input").addEventListener("input", controls);
  $("message-input").addEventListener("compositionstart", () => { state.composing = true; });
  $("message-input").addEventListener("compositionend", () => { state.composing = false; });
  $("message-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !state.composing) { event.preventDefault(); $("chat-form").requestSubmit(); } });
  $("reset-button").addEventListener("click", () => reset());
  $("buyer-select").addEventListener("change", (event) => reset(event.target.value));
  reset();
})();
