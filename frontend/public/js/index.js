
    function esc(s) {
    return String(s || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function safeParseJSON(text) {
    try { return JSON.parse(text); } catch { return null; }
    }

    function normalizeClassStr(s) {
    return String(s || "").trim().replace(/\s+/g, " ");
    }

    function sessionsKey() { return "transferSessions:v1"; }
    function pairKey(fromCode, toCode) { return String(fromCode) + "-" + String(toCode); }
    function matchesKey(fromCode, toCode) { return "transferMatches:v1:" + String(fromCode) + "-" + String(toCode); }

    function loadSessions() {
    try {
        const parsed = safeParseJSON(localStorage.getItem(sessionsKey()) || "{}");
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch { return {}; }
    }

    function saveSessions(obj) {
    try { localStorage.setItem(sessionsKey(), JSON.stringify(obj || {})); return true; }
    catch { return false; }
    }

    function mergeUnique(existingArr, newArr) {
    const set = new Set((existingArr || []).map(normalizeClassStr).filter(Boolean));
    (newArr || []).map(normalizeClassStr).filter(Boolean).forEach(v => set.add(v));
    return Array.from(set);
    }

    function upsertSession(fromCode, toCode, fromName, toName, classes) {
    const sessions = loadSessions();
    const key = pairKey(fromCode, toCode);
    const now = Date.now();

    const prev = sessions[key] || {
        fromCode: String(fromCode),
        toCode: String(toCode),
        fromName: String(fromName || ""),
        toName: String(toName || ""),
        updatedAt: now,
        classes: []
    };

    sessions[key] = {
        fromCode: String(fromCode),
        toCode: String(toCode),
        fromName: String(fromName || prev.fromName || ""),
        toName: String(toName || prev.toName || ""),
        updatedAt: now,
        classes: mergeUnique(prev.classes, classes)
    };

    saveSessions(sessions);
    }

    function formatDateTime(ms) {
    try { return new Date(ms).toLocaleString(); }
    catch { return ""; }
    }

    function setWarning(msg) {
    const el = document.getElementById("warning");
    if (!msg) {
        el.style.display = "none";
        el.textContent = "";
        return;
    }
    el.style.display = "block";
    el.textContent = msg;
    }

    // Sidebar (vanilla)
    function openSidebar() {
    const sidebar = document.getElementById("historySidebar");
    const overlay = document.getElementById("overlay");
    sidebar.classList.add("open");
    overlay.classList.add("open");
    overlay.hidden = false;
    sidebar.setAttribute("aria-hidden", "false");
    document.getElementById("historyToggle").setAttribute("aria-expanded", "true");
    renderHistory();
    }

    function closeSidebar() {
    const sidebar = document.getElementById("historySidebar");
    const overlay = document.getElementById("overlay");
    sidebar.classList.remove("open");
    overlay.classList.remove("open");
    sidebar.setAttribute("aria-hidden", "true");
    document.getElementById("historyToggle").setAttribute("aria-expanded", "false");
    window.setTimeout(() => {
        if (!overlay.classList.contains("open")) overlay.hidden = true;
    }, 0);
    }

    function renderHistory() {
    const sessions = loadSessions();
    const keys = Object.keys(sessions || {});
    const list = document.getElementById("historyList");
    const empty = document.getElementById("historyEmpty");

    keys.sort((a, b) => (sessions[b].updatedAt || 0) - (sessions[a].updatedAt || 0));

    list.innerHTML = "";
    empty.style.display = keys.length ? "none" : "block";

    keys.forEach((k) => {
        const s = sessions[k] || {};
        const fromCode = s.fromCode;
        const toCode = s.toCode;

        const fromName = s.fromName || fromCode || "?";
        const toName = s.toName || toCode || "?";
        const updated = formatDateTime(s.updatedAt || 0);
        const classes = Array.isArray(s.classes) ? s.classes : [];

        const item = document.createElement("div");
        item.className = "history-item";
        item.innerHTML = `
        <div class="history-item-title">${esc(fromName)} → ${esc(toName)}</div>
        <div class="history-item-meta">From: ${esc(fromCode || "?")} • To: ${esc(toCode || "?")} • Updated: ${esc(updated)} • Classes: ${esc(classes.length)}</div>
        <div class="history-item-actions">
            <button class="button" type="button" data-load="1">Load</button>
            <button class="button" type="button" data-delete="1">Delete</button>
            <button class="button" type="button" data-results="1">Results</button>
        </div>
        `;

        item.querySelector("[data-delete='1']").addEventListener("click", () => {
        const sessionsNow = loadSessions();
        delete sessionsNow[pairKey(fromCode, toCode)];
        saveSessions(sessionsNow);

        // also remove matches for this pair
        try { localStorage.removeItem(matchesKey(fromCode, toCode)); } catch {}

        renderHistory();
        });

        item.querySelector("[data-load='1']").addEventListener("click", () => {
        document.getElementById("fromInput").value = fromName || "";
        document.getElementById("toInput").value = toName || "";

        const rowsEl = document.getElementById("rows");
        rowsEl.innerHTML = "";

        const cls = classes.slice(0, 30);
        const minRows = Math.max(3, cls.length || 3);
        for (let i = 0; i < minRows; i++) createRow(rowsEl, cls[i] || "");

        closeSidebar();
        validate();
        });

        item.querySelector("[data-results='1']").addEventListener("click", () => {
        try { localStorage.setItem("takenClasses", JSON.stringify(classes.slice(0, 30))); } catch {}
        closeSidebar();
        window.location.href = `/results?from=${encodeURIComponent(fromCode)}&to=${encodeURIComponent(toCode)}`;
        });

        list.appendChild(item);
    });
    }

    const nameToCode = new Map();

    function getSelectedCode(inputEl) {
    return nameToCode.get(String(inputEl.value || "").trim()) || "";
    }

    function validate() {
    const submit = document.getElementById("submit");
    const fromInput = document.getElementById("fromInput");
    const toInput = document.getElementById("toInput");
    submit.disabled = !getSelectedCode(fromInput) || !getSelectedCode(toInput);
    }

    function createRow(rowsEl, value) {
    const row = document.createElement("div");
    row.className = "class-row";
    row.innerHTML = `
        <input class="input" placeholder="e.g. HORT 53" value="${esc(value)}">
        <button class="button" type="button">Remove</button>
    `;
    row.querySelector("button").onclick = () => row.remove();
    rowsEl.appendChild(row);
    }

    async function init() {
    // Sidebar wiring
    document.getElementById("historyToggle").addEventListener("click", openSidebar);
    document.getElementById("historyClose").addEventListener("click", closeSidebar);
    document.getElementById("overlay").addEventListener("click", closeSidebar);
    window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSidebar(); });

    document.getElementById("refreshHistory").addEventListener("click", renderHistory);
    document.getElementById("clearHistory").addEventListener("click", () => {
        try {
        localStorage.removeItem("transferSessions:v1");
        Object.keys(localStorage).forEach(k => {
            if (String(k).startsWith("transferMatches:v1:")) localStorage.removeItem(k);
        });
        } catch {}
        renderHistory();
    });

    const fromInput = document.getElementById("fromInput");
    const toInput = document.getElementById("toInput");
    const list = document.getElementById("schoolsList");
    const rowsEl = document.getElementById("rows");

    // Seed rows
    for (let i = 0; i < 3; i++) createRow(rowsEl, "");
    document.getElementById("addRow").onclick = () => createRow(rowsEl, "");

    // Fetch schools
    try {
        const res = await fetch("/schools");
        const schools = await res.json();

        schools.forEach(s => {
        nameToCode.set(s.schoolName, String(s.code));
        const opt = document.createElement("option");
        opt.value = s.schoolName;
        list.appendChild(opt);
        });
    } catch (e) {
        setWarning("Could not load schools list. Is the backend running?");
    }

    fromInput.addEventListener("input", validate);
    toInput.addEventListener("input", validate);

    // Restore last taken classes (optional)
    try {
        const raw = localStorage.getItem("takenClasses");
        const saved = raw ? JSON.parse(raw) : [];
        if (Array.isArray(saved) && saved.length) {
        rowsEl.innerHTML = "";
        const cls = saved.slice(0, 30);
        const minRows = Math.max(3, cls.length || 3);
        for (let i = 0; i < minRows; i++) createRow(rowsEl, cls[i] || "");
        }
    } catch {}

    validate();

    document.getElementById("submit").onclick = () => {
        setWarning("");

        const fromCode = getSelectedCode(fromInput);
        const toCode = getSelectedCode(toInput);

        if (!fromCode || !toCode) {
        setWarning("Please select valid schools from the list.");
        return;
        }

        const classes = [...rowsEl.querySelectorAll("input")]
        .map(i => normalizeClassStr(i.value))
        .filter(Boolean)
        .slice(0, 30);

        try { localStorage.setItem("takenClasses", JSON.stringify(classes)); } catch {}

        // Save session (same schema used by results)
        upsertSession(fromCode, toCode, fromInput.value.trim(), toInput.value.trim(), classes);

        window.location.href = `/results?from=${encodeURIComponent(fromCode)}&to=${encodeURIComponent(toCode)}`;
    };
    }

    window.addEventListener("DOMContentLoaded", init);
