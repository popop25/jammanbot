const STORAGE_KEYS = {
  profile: "jammanbot.profile.v2",
  records: "jammanbot.records.v2",
  messages: "jammanbot.messages.v2",
  context: "jammanbot.context.v2",
};

const BOT_AVATAR = "/static/image.png";
const USER_AVATAR =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' viewBox='0 0 80 80'%3E%3Crect width='80' height='80' rx='18' fill='%232563eb'/%3E%3Ccircle cx='40' cy='31' r='13' fill='white' opacity='.95'/%3E%3Cpath d='M18 66c4-15 14-23 22-23s18 8 22 23' fill='white' opacity='.95'/%3E%3C/svg%3E";

let cafeteriaOptions = {};
let busy = false;

const $ = (id) => document.getElementById(id);

function loadJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function getProfile() {
  return loadJson(STORAGE_KEYS.profile, { campus: "BD", cafeteria: "21" });
}

function setProfile(profile) {
  saveJson(STORAGE_KEYS.profile, profile);
}

function getRecords() {
  return loadJson(STORAGE_KEYS.records, []);
}

function setRecords(records) {
  saveJson(STORAGE_KEYS.records, records);
}

function getMessages() {
  return loadJson(STORAGE_KEYS.messages, []);
}

function setMessages(messages) {
  saveJson(STORAGE_KEYS.messages, messages);
}

function getContext() {
  return loadJson(STORAGE_KEYS.context, {});
}

function setContext(context) {
  saveJson(STORAGE_KEYS.context, context);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

async function init() {
  await loadOptions();
  restoreSettings();
  bindEvents();
  renderMessages();
  resizeInput();
}

async function loadOptions() {
  const data = await api("/api/cafeteria/options");
  cafeteriaOptions = data.options || {};
  const campusSelect = $("campusSelect");
  campusSelect.innerHTML = Object.keys(cafeteriaOptions)
    .map((campus) => `<option value="${escapeHtml(campus)}">${escapeHtml(campus)}</option>`)
    .join("");
  campusSelect.addEventListener("change", renderCafeterias);
}

function renderCafeterias() {
  const campus = $("campusSelect").value || "BD";
  const options = cafeteriaOptions[campus] || {};
  $("cafeteriaSelect").innerHTML = Object.entries(options)
    .map(([seq, name]) => `<option value="${escapeHtml(seq)}">${escapeHtml(name)}</option>`)
    .join("");
}

function restoreSettings() {
  const profile = getProfile();
  $("campusSelect").value = profile.campus || "BD";
  renderCafeterias();
  $("cafeteriaSelect").value = profile.cafeteria || "21";
}

function bindEvents() {
  $("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    sendCurrentMessage();
  });
  $("messageInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendCurrentMessage();
    }
  });
  $("messageInput").addEventListener("input", resizeInput);
  $("settingsToggle").addEventListener("click", () => {
    $("settingsPanel").hidden = !$("settingsPanel").hidden;
  });
  $("saveSettingsBtn").addEventListener("click", () => {
    const profile = {
      campus: $("campusSelect").value || "BD",
      cafeteria: $("cafeteriaSelect").value || "21",
    };
    setProfile(profile);
    appendMessage({
      role: "bot",
      text: `음... 앞으로 ${cafeteriaLabel(profile)} 기준으로 볼게.`,
      type: "setting",
    });
    $("settingsPanel").hidden = true;
  });
  $("clearChatBtn").addEventListener("click", () => {
    if (!confirm("대화와 식사 기록을 모두 지울까요?")) return;
    setMessages([]);
    setRecords([]);
    setContext({});
    renderMessages();
  });
  for (const button of document.querySelectorAll("[data-prompt]")) {
    button.addEventListener("click", () => sendMessage(button.dataset.prompt));
  }
}

async function sendCurrentMessage() {
  const input = $("messageInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  resizeInput();
  await sendMessage(text);
}

async function sendMessage(text) {
  if (busy) return;
  busy = true;
  setComposerEnabled(false);

  appendMessage({ role: "user", text, type: "text" });
  const loadingId = appendMessage({ role: "bot", text: "음...", type: "loading", loading: true });

  try {
    const data = await api("/api/agent/message", {
      method: "POST",
      body: JSON.stringify({
        text,
        profile: getProfile(),
        records: getRecords(),
        messages: getMessages().slice(-20),
        context: getContext(),
      }),
    });
    removeMessage(loadingId);
    applyAgentResult(data);
  } catch (error) {
    updateMessage(loadingId, {
      role: "bot",
      text: `앗, 읽다가 멈췄어. ${cleanError(error.message)}`,
      type: "error",
      loading: false,
    });
  } finally {
    busy = false;
    setComposerEnabled(true);
    $("messageInput").focus();
  }
}

function applyAgentResult(data) {
  if (data.record) {
    setRecords([data.record, ...getRecords()]);
  }
  if (data.profilePatch) {
    const nextProfile = { ...getProfile(), ...data.profilePatch };
    setProfile(nextProfile);
    restoreSettings();
  }
  if (data.contextPatch) {
    setContext({ ...getContext(), ...data.contextPatch });
  }
  appendMessage({
    role: "bot",
    text: data.reply || "음...",
    type: data.type || "chat",
    attachments: data.attachments || [],
  });
}

function appendMessage(message) {
  const item = {
    id: message.id || crypto.randomUUID(),
    createdAt: message.createdAt || new Date().toISOString(),
    ...message,
  };
  setMessages([...getMessages(), item]);
  renderMessages();
  return item.id;
}

function updateMessage(id, patch) {
  setMessages(getMessages().map((message) => (message.id === id ? { ...message, ...patch } : message)));
  renderMessages();
}

function removeMessage(id) {
  setMessages(getMessages().filter((message) => message.id !== id));
  renderMessages();
}

function renderMessages() {
  const messages = getMessages();
  $("emptyState").hidden = messages.length > 0;
  const list = $("messageList");
  const template = $("messageTemplate");
  list.innerHTML = "";

  for (const message of messages) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.classList.add(message.role);
    if (message.loading) node.classList.add("loading");
    const avatar = node.querySelector(".message-avatar");
    avatar.src = message.role === "bot" ? BOT_AVATAR : USER_AVATAR;
    avatar.alt = message.role === "bot" ? "잠만봇" : "나";
    node.querySelector(".message-meta strong").textContent = message.role === "bot" ? "잠만봇" : "나";
    node.querySelector("time").textContent = formatTime(message.createdAt);
    node.querySelector(".bubble").textContent = message.text || "";
    renderAttachments(node.querySelector(".attachments"), message.attachments || []);
    list.appendChild(node);
  }
  requestAnimationFrame(() => {
    list.scrollTop = list.scrollHeight;
  });
}

function renderAttachments(root, attachments) {
  root.innerHTML = "";
  for (const attachment of attachments) {
    if (attachment.kind === "menu") {
      root.appendChild(renderMenuAttachment(attachment.menu));
    } else if (attachment.kind === "roulette") {
      root.appendChild(renderRouletteAttachment(attachment.choice));
    } else if (attachment.kind === "stats") {
      root.appendChild(renderStatsAttachment(attachment.stats));
    }
  }
}

function renderMenuAttachment(menu) {
  const wrapper = document.createElement("div");
  wrapper.className = "menu-attachment";
  const images = (menu.items || []).filter((item) => item.image_url);
  if (!images.length) {
    wrapper.innerHTML = `<div class="attachment-line">사진은 아직 안 올라온 것 같아.</div>`;
    return wrapper;
  }

  const grid = document.createElement("div");
  grid.className = "menu-images";
  for (const item of images) {
    const card = document.createElement("div");
    card.className = "menu-image-card";
    card.innerHTML = `
      <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.course)} ${escapeHtml(item.name)}" loading="lazy" />
      <span>${escapeHtml(item.course)} · ${escapeHtml(item.name)}</span>
    `;
    grid.appendChild(card);
  }
  wrapper.appendChild(grid);
  return wrapper;
}

function renderRouletteAttachment(choice) {
  const wrapper = document.createElement("div");
  wrapper.className = "roulette-attachment";
  wrapper.innerHTML = `<strong>${escapeHtml(choice?.name || "오늘의 메뉴")}</strong><span>${escapeHtml((choice?.tags || []).join(" · "))}</span>`;
  return wrapper;
}

function renderStatsAttachment(stats) {
  const wrapper = document.createElement("div");
  wrapper.className = "stats-attachment";
  const top = (stats.topMenus || [])
    .slice(0, 3)
    .map((item) => `${item.name} ${item.count}회`)
    .join(" · ");
  wrapper.innerHTML = `
    <strong>기록 ${Number(stats.total || 0)}끼</strong>
    <span>구내식당 ${Number(stats.cafeteriaCount || 0)}번 · 외식 ${Number(stats.outsideCount || 0)}번</span>
    ${top ? `<div class="attachment-line">${escapeHtml(top)}</div>` : ""}
  `;
  return wrapper;
}

function cafeteriaLabel(profile) {
  return cafeteriaOptions[profile.campus]?.[profile.cafeteria] || "분당캠퍼스 비원";
}

function resizeInput() {
  const input = $("messageInput");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
}

function setComposerEnabled(enabled) {
  $("messageInput").disabled = !enabled;
  $("sendBtn").disabled = !enabled;
}

function formatTime(value) {
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return "";
  }
}

function cleanError(message) {
  try {
    const parsed = JSON.parse(message);
    return parsed.detail || message;
  } catch {
    return message;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

init();
