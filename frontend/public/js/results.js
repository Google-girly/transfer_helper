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

    // ---- Storage keys ----
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

    function normalizeClassStr(s) {
    return String(s || "").trim().replace(/\s+/g, " ");
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

    function loadMatches(fromCode, toCode) {
    try {
        const parsed = safeParseJSON(localStorage.getItem(matchesKey(fromCode, toCode)) || "{}");
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch { return {}; }
    }

    function saveMatches(from, to, results) {
    try {
        const key = matchesKey(from, to);
        const existing = loadMatches(from, to);

        (results || []).forEach(function (r) {
        if (!r || !r.matches_count) return;

        const matchedCourses = [];
        (r.matches || []).forEach(function (m) {
            if (m && m.matched_equivalent && m.matched_equivalent.course) {
            matchedCourses.push(m.matched_equivalent.course);
            }
        });

        existing[r.query] = {
            matchedCourses: matchedCourses,
            timestamp: Date.now()
        };
        });

        localStorage.setItem(key, JSON.stringify(existing));
        return true;
    } catch {
        return false;
    }
    }

    function formatDateTime(ms) {
    try { return new Date(ms).toLocaleString(); }
    catch { return ""; }
    }

    async function fetchJSONOrText(url, options) {
    const res = await fetch(url, options);
    const text = await res.text();
    const parsed = safeParseJSON(text);
    return { res, parsed, text };
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
            <button class="button" type="button" data-open="1">Open Results</button>
            <button class="button" type="button" data-delete="1">Delete</button>
        </div>
        `;

        item.querySelector("[data-open='1']").addEventListener("click", () => {
        try { localStorage.setItem("takenClasses", JSON.stringify(classes.slice(0, 30))); } catch {}
        closeSidebar();
        window.location.href = `/results?from=${encodeURIComponent(fromCode)}&to=${encodeURIComponent(toCode)}`;
        });

        item.querySelector("[data-delete='1']").addEventListener("click", () => {
        const sessionsNow = loadSessions();
        delete sessionsNow[pairKey(fromCode, toCode)];
        saveSessions(sessionsNow);
        try { localStorage.removeItem(matchesKey(fromCode, toCode)); } catch {}
        renderHistory();
        });

        list.appendChild(item);
    });
    }

    function renderResults(data, stored) {
    const summary = document.getElementById("summary");
    const takenBlock = document.getElementById("takenBlock");
    const savedCount = Object.keys(stored || {}).length;

    summary.innerHTML = `
        <div class="notice">
        <div><strong>From:</strong> ${esc(data.from_college)}</div>
        <div><strong>To:</strong> ${esc(data.to_college)}</div>
        <div><strong>Articulation Year:</strong> ${esc(data.academic_year || "N/A")}</div>
        <div><strong>GE List:</strong> ${esc(data.geListType || "N/A")}</div>
        <div><strong>Saved matches (this pair):</strong> ${esc(savedCount)}</div>
        </div>
    `;

    const results = Array.isArray(data.results) ? data.results : [];
    if (!results.length) {
        takenBlock.innerHTML = `<div class="notice">No results returned.</div>`;
        return;
    }

    takenBlock.innerHTML = results.map(function (r) {
        const isStored = Object.prototype.hasOwnProperty.call(stored, r.query);
        const savedBadge = isStored ? `<span class="badge">Saved</span>` : "";

        if (!r.matches_count) {
        return `
            <div class="result-item">
            <div class="row between">
                <div><strong>${esc(r.query)}</strong></div>
                <div>${savedBadge}</div>
            </div>
            <div class="small">No match found.</div>
            </div>
        `;
        }

        const matchesHtml = (r.matches || []).map(function (m) {
        const matchedCourse =
            (m && m.matched_equivalent && m.matched_equivalent.course) ? m.matched_equivalent.course : "";
        const matchedTitle =
            (m && m.matched_equivalent && m.matched_equivalent.title) ? m.matched_equivalent.title : "";

        const geHtml = m.ge ? `
            <div class="notice" style="margin-top:8px;">
            <div><strong>Transfer Areas:</strong> ${esc((m.ge.transferAreas || []).join(", ") || "None")}</div>
            <div><strong>Approved:</strong> ${m.ge.isCurrentlyApproved ? "Yes" : "No"}</div>
            </div>
        ` : "";

        return `
            <div class="match-item">
            <div><strong>${esc(m.from_course)}</strong> — ${esc(m.course_title)}</div>
            <div class="small">Matched: ${esc(matchedCourse)}${matchedTitle ? " — " + esc(matchedTitle) : ""}</div>
            ${geHtml}
            </div>
        `;
        }).join("");

        return `
        <div class="result-item">
            <div class="row between">
            <div><strong>${esc(r.query)}</strong></div>
            <div>${savedBadge}</div>
            </div>
            ${matchesHtml}
        </div>
        `;
    }).join("");
    }

    async function main() {
    // Sidebar wiring
    document.getElementById("historyToggle").addEventListener("click", openSidebar);
    document.getElementById("historyClose").addEventListener("click", closeSidebar);
    document.getElementById("overlay").addEventListener("click", closeSidebar);
    window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSidebar(); });

    document.getElementById("refreshHistory").onclick = renderHistory;
    document.getElementById("clearHistory").onclick = () => {
        try {
        localStorage.removeItem("transferSessions:v1");
        Object.keys(localStorage).forEach(k => {
            if (String(k).startsWith("transferMatches:v1:")) localStorage.removeItem(k);
        });
        } catch {}
        renderHistory();
    };

    const params = new URLSearchParams(window.location.search);
    const from = params.get("from");
    const to = params.get("to");

    const summary = document.getElementById("summary");
    const takenBlock = document.getElementById("takenBlock");

    if (!from || !to) {
        summary.innerHTML = `<div class="notice">Missing school selection.</div>`;
        return;
    }

    let taken = [];
    try { taken = JSON.parse(localStorage.getItem("takenClasses") || "[]"); } catch {}

    if (!taken.length) {
        summary.innerHTML = `<div class="notice">No classes were entered on the home page.</div>`;
        return;
    }

    summary.innerHTML = `<div class="notice">Finding transfer matches…</div>`;
    takenBlock.innerHTML = "";

    try {
        const payload = {
        from: from,
        to: to,
        queries: taken,
        geListType: "CALGETC",
        geAcademicYearId: 76
        };

        const { res, parsed, text } = await fetchJSONOrText("http://localhost:8000/lookup_batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
        });

        if (!parsed) {
        summary.innerHTML = `
            <div class="notice">
            Backend did not return JSON.
            <div class="small"><strong>Status:</strong> ${esc(res.status)} ${esc(res.statusText)}</div>
            <pre class="codeblock">${esc(text)}</pre>
            </div>
        `;
        return;
        }

        const data = parsed;

        if (!res.ok) {
        summary.innerHTML = `<div class="notice">${esc(data.error || "Lookup failed")}</div>`;
        return;
        }

        // Save matches + update the session so history reflects newest run
        saveMatches(from, to, data.results || []);
        upsertSession(from, to, data.from_college, data.to_college, taken);

        const storedAfter = loadMatches(from, to);
        renderResults(data, storedAfter);

    } catch (err) {
        summary.innerHTML = `
        <div class="notice">
            Lookup failed in the browser.
            <pre class="codeblock">${esc(err && err.message ? err.message : String(err))}</pre>
        </div>
        `;
    }
    }

    window.addEventListener("DOMContentLoaded", main);
