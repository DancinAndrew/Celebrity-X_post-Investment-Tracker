"use strict";
(() => {
  const metadata = JSON.parse(document.getElementById("snapshot-metadata").textContent);
  const theme = document.getElementById("theme");
  const setTheme = value => {
    if (value === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = value;
  };
  try {
    const saved = localStorage.getItem("xpost-tracker-theme");
    if (["auto", "light", "dark"].includes(saved)) theme.value = saved;
  } catch (_) { /* Browser storage may be disabled. */ }
  setTheme(theme.value);
  theme.addEventListener("change", () => {
    setTheme(theme.value);
    try { localStorage.setItem("xpost-tracker-theme", theme.value); } catch (_) {}
  });

  const groups = Array.from(document.querySelectorAll("details.dt"));
  const summaries = groups.map(group => group.querySelector("summary").textContent.toLocaleLowerCase());
  const input = document.getElementById("history-search");
  const count = document.getElementById("search-count");
  const filter = () => {
    const query = input.value.trim().toLocaleLowerCase();
    let visible = 0;
    groups.forEach((group, index) => {
      group.hidden = query !== "" && !summaries[index].includes(query);
      if (!group.hidden) visible += 1;
    });
    count.textContent = query ? `符合 ${visible} 個歷史區塊。共識、揭露表與抓取紀錄維持原始內容。` : `共 ${groups.length} 個歷史區塊。點開可看原文與判讀理由。`;
  };
  input.addEventListener("input", filter);
  document.getElementById("clear-search").addEventListener("click", () => {
    input.value = ""; filter(); input.focus();
  });
  filter();

  const updateAge = () => {
    const age = Math.max(0, (Date.now() - Date.parse(metadata.last_fetch_completed_at_utc)) / 3600000);
    const display = age < 1 ? `${Math.floor(age * 60)} 分鐘` : `${age.toFixed(1)} 小時`;
    const stale = age > metadata.stale_after_hours;
    document.getElementById("snapshot-age").textContent = `${display}前嘗試收集 · ${stale ? "資料已過期，等待新版快照" : "目前為手動匯出快照"}`;
    const badge = document.getElementById("pipeline-state");
    badge.classList.toggle("stale", stale);
    badge.textContent = stale ? "資料過期" : metadata.pipeline_state === "partial" ? "部分正常" : "本輪完成";
  };
  updateAge();
  setInterval(updateAge, 60000);
})();
