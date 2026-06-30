const STORAGE_KEYS = {
  profile: "jammanbot.profile.v1",
  records: "jammanbot.records.v1",
  candidates: "jammanbot.candidates.v1",
};

const MEAL_LABELS = { BF: "아침", LN: "점심", DN: "저녁", SN: "야식" };
let currentMenu = null;
let cafeteriaOptions = {};

const $ = (id) => document.getElementById(id);

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

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

function profile() {
  return loadJson(STORAGE_KEYS.profile, { campus: "BD", cafeteria: "21" });
}

function records() {
  return loadJson(STORAGE_KEYS.records, []);
}

function setRecords(value) {
  saveJson(STORAGE_KEYS.records, value);
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
  $("dateInput").value = todayIso();
  await loadOptions();
  restoreProfile();
  await loadDefaults();
  bindEvents();
  await loadMenu();
  renderRecords();
  await summarizePattern(false);
}

async function loadOptions() {
  const data = await api("/api/cafeteria/options");
  cafeteriaOptions = data.options || {};
  const campusSelect = $("campusSelect");
  campusSelect.innerHTML = Object.keys(cafeteriaOptions)
    .map((campus) => `<option value="${campus}">${campus}</option>`)
    .join("");
  campusSelect.addEventListener("change", renderCafeterias);
}

function renderCafeterias() {
  const selectedCampus = $("campusSelect").value || "BD";
  const options = cafeteriaOptions[selectedCampus] || {};
  $("cafeteriaSelect").innerHTML = Object.entries(options)
    .map(([seq, name]) => `<option value="${seq}">${name}</option>`)
    .join("");
}

function restoreProfile() {
  const saved = profile();
  $("campusSelect").value = saved.campus || "BD";
  renderCafeterias();
  $("cafeteriaSelect").value = saved.cafeteria || "21";
}

async function loadDefaults() {
  const saved = loadJson(STORAGE_KEYS.candidates, null);
  if (saved) {
    renderCandidates(saved);
    return;
  }
  const data = await api("/api/recommend/defaults");
  saveJson(STORAGE_KEYS.candidates, data.candidates || []);
  renderCandidates(data.candidates || []);
}

function bindEvents() {
  $("saveProfileBtn").addEventListener("click", () => {
    saveJson(STORAGE_KEYS.profile, {
      campus: $("campusSelect").value,
      cafeteria: $("cafeteriaSelect").value,
    });
    loadMenu();
  });
  $("loadMenuBtn").addEventListener("click", loadMenu);
  $("parseMealBtn").addEventListener("click", parseNaturalMeal);
  $("chatBtn").addEventListener("click", chat);
  $("rouletteBtn").addEventListener("click", roulette);
  $("summarizeBtn").addEventListener("click", () => summarizePattern(true));
  $("clearRecordsBtn").addEventListener("click", () => {
    if (confirm("식사 기록을 모두 삭제할까요?")) {
      setRecords([]);
      renderRecords();
      summarizePattern(false);
    }
  });
}

async function loadMenu() {
  const selectedProfile = {
    campus: $("campusSelect").value || "BD",
    cafeteria: $("cafeteriaSelect").value || "21",
  };
  saveJson(STORAGE_KEYS.profile, selectedProfile);
  const params = new URLSearchParams({
    date: $("dateInput").value || todayIso(),
    meal: $("mealSelect").value,
    campus: selectedProfile.campus,
    cafeteria: selectedProfile.cafeteria,
  });
  setBusy("loadMenuBtn", true);
  try {
    currentMenu = await api(`/api/cafeteria/menu?${params}`);
    $("todayMeta").textContent = `${currentMenu.restaurantName} · ${MEAL_LABELS[currentMenu.mealType]}`;
    renderMenu(currentMenu);
  } catch (error) {
    $("menuGrid").innerHTML = `<div class="panel">메뉴를 가져오지 못했습니다. ${escapeHtml(error.message)}</div>`;
  } finally {
    setBusy("loadMenuBtn", false);
  }
}

function renderMenu(menu) {
  const grid = $("menuGrid");
  if (!menu.items?.length) {
    grid.innerHTML = `<div class="panel">음... ${menu.date} ${MEAL_LABELS[menu.mealType]} 메뉴는 아직 안 보여.</div>`;
    return;
  }
  const template = $("menuCardTemplate");
  grid.innerHTML = "";
  for (const item of menu.items) {
    const node = template.content.cloneNode(true);
    node.querySelector(".course").textContent = item.course;
    node.querySelector(".soldout").textContent = item.soldout ? "품절" : "";
    node.querySelector(".menu-name").textContent = item.name;
    const image = node.querySelector(".menu-image");
    if (item.image_url) {
      image.innerHTML = `<img src="${item.image_url}" alt="${escapeHtml(item.name)}" />`;
    } else {
      image.textContent = "이미지 준비중";
    }
    for (const button of node.querySelectorAll("[data-rating]")) {
      button.addEventListener("click", () => addRecordFromMenu(item, button.dataset.rating));
    }
    grid.appendChild(node);
  }
}

function addRecordFromMenu(item, rating) {
  const menu = currentMenu || {};
  const record = {
    id: String(Date.now()),
    date: menu.date || todayIso(),
    mealType: menu.mealType || "LN",
    place: "cafeteria",
    menuName: `${item.course}: ${item.name}`,
    rating,
    createdAt: new Date().toISOString(),
  };
  setRecords([record, ...records()]);
  $("agentReply").textContent = `음... ${record.menuName} 기록했어. 먹은 건 중요하지.`;
  renderRecords();
  summarizePattern(false);
}

async function parseNaturalMeal() {
  const text = $("agentInput").value.trim();
  if (!text) return;
  setBusy("parseMealBtn", true);
  try {
    const record = await api("/api/agent/parse-meal", {
      method: "POST",
      body: JSON.stringify({ text, menu: currentMenu }),
    });
    setRecords([record, ...records()]);
    $("agentReply").textContent = `음... ${record.menuName} 기록했어.`;
    $("agentInput").value = "";
    renderRecords();
    summarizePattern(false);
  } catch (error) {
    $("agentReply").textContent = `기록 실패: ${error.message}`;
  } finally {
    setBusy("parseMealBtn", false);
  }
}

async function chat() {
  const text = $("agentInput").value.trim();
  if (!text) return;
  setBusy("chatBtn", true);
  try {
    const data = await api("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({ text, records: records() }),
    });
    $("agentReply").textContent = data.reply;
  } catch (error) {
    $("agentReply").textContent = `응답 실패: ${error.message}`;
  } finally {
    setBusy("chatBtn", false);
  }
}

async function roulette() {
  setBusy("rouletteBtn", true);
  try {
    const data = await api("/api/recommend/roulette", {
      method: "POST",
      body: JSON.stringify({
        candidates: loadJson(STORAGE_KEYS.candidates, []),
        mood: "",
        records: records(),
      }),
    });
    $("rouletteResult").innerHTML = `<strong>${escapeHtml(data.choice.name)}</strong><br>${escapeHtml(data.reason)}`;
  } finally {
    setBusy("rouletteBtn", false);
  }
}

async function summarizePattern(showLoading) {
  if (showLoading) setBusy("summarizeBtn", true);
  try {
    const data = await api("/api/agent/summarize-pattern", {
      method: "POST",
      body: JSON.stringify({ records: records() }),
    });
    renderStats(data);
    $("patternSummary").textContent = data.agentSummary;
  } catch (error) {
    $("patternSummary").textContent = `요약 실패: ${error.message}`;
  } finally {
    if (showLoading) setBusy("summarizeBtn", false);
  }
}

function renderStats(stats) {
  $("stats").innerHTML = [
    stat("총 기록", stats.total || 0),
    stat("구내식당", stats.cafeteriaCount || 0),
    stat("좋았던 끼니", stats.goodCount || 0),
  ].join("");
}

function stat(label, value) {
  return `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`;
}

function renderRecords() {
  const list = $("recordList");
  const items = records();
  if (!items.length) {
    list.innerHTML = `<p class="agent-reply">아직 기록이 없습니다. 메뉴 카드에서 만족도를 누르거나 자연어로 기록하세요.</p>`;
    return;
  }
  list.innerHTML = items
    .slice(0, 20)
    .map(
      (record) => `
        <div class="record">
          <small>${escapeHtml(record.date)} · ${MEAL_LABELS[record.mealType] || record.mealType}</small>
          <div>${escapeHtml(record.menuName)}</div>
          <small>${ratingLabel(record.rating)}</small>
        </div>
      `,
    )
    .join("");
}

function renderCandidates(candidates) {
  $("candidateList").innerHTML = candidates.map((item) => `<span class="chip">${escapeHtml(item.name)}</span>`).join("");
}

function ratingLabel(rating) {
  if (rating === "good") return "좋음";
  if (rating === "bad") return "별로";
  return "보통";
}

function setBusy(id, busy) {
  const el = $(id);
  el.disabled = busy;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

init();
