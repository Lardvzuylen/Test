// Webapp JS (Dataiku Standard webapp -> tab "JavaScript").
// Gebruikt getWebAppBackendUrl(...) (door Dataiku geleverd) om de Python-backend
// aan te roepen. Coordinaten zijn genormaliseerd (0..1, oorsprong linksboven),
// dus de overlay matcht exact met het echte lakken.

(function () {
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

  const state = {
    caseId: null,
    redactions: [],   // bestaande (met redaction_id) + nieuw toegevoegde (temp_*)
    pageSizes: {},     // page_no -> {w, h} in CSS-pixels van de overlay
  };

  const $ = (id) => document.getElementById(id);

  function api(path) { return getWebAppBackendUrl(path); }

  async function loadCases() {
    const status = $("status-filter").value;
    const res = await fetch(api("cases" + (status ? "?status=" + status : "")));
    const cases = await res.json();
    const ul = $("case-list");
    ul.innerHTML = "";
    cases.forEach((c) => {
      const li = document.createElement("li");
      li.textContent = c.filename + (c.used_ocr ? "  [OCR]" : "");
      li.title = c.status;
      li.onclick = () => openCase(c);
      ul.appendChild(li);
    });
  }

  async function openCase(c) {
    state.caseId = c.case_id;
    $("case-title").textContent = c.filename;
    $("ocr-badge").classList.toggle("hidden", !c.used_ocr);
    $("btn-save").disabled = false;
    $("btn-approve").disabled = false;

    const [redRes] = await Promise.all([fetch(api("redactions/" + c.case_id))]);
    state.redactions = await redRes.json();

    const pdfData = await (await fetch(api("pdf/" + c.case_id))).arrayBuffer();
    await renderPdf(pdfData);
    renderEntityList();
  }

  async function renderPdf(data) {
    const viewer = $("viewer");
    viewer.innerHTML = "";
    state.pageSizes = {};

    const pdf = await pdfjsLib.getDocument({ data }).promise;
    for (let p = 1; p <= pdf.numPages; p++) {
      const page = await pdf.getPage(p);
      const viewport = page.getViewport({ scale: 1.4 });

      const wrap = document.createElement("div");
      wrap.className = "page-wrap";
      wrap.style.width = viewport.width + "px";
      wrap.style.height = viewport.height + "px";

      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      const overlay = document.createElement("div");
      overlay.className = "overlay";
      overlay.dataset.pageNo = p - 1; // 0-based, zoals in de database

      wrap.appendChild(canvas);
      wrap.appendChild(overlay);
      viewer.appendChild(wrap);

      state.pageSizes[p - 1] = { w: viewport.width, h: viewport.height };
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

      enableDragToAdd(overlay, p - 1);
    }
    drawBoxes();
  }

  function drawBoxes() {
    document.querySelectorAll(".overlay").forEach((o) => (o.innerHTML = ""));
    state.redactions.forEach((r) => {
      const overlay = document.querySelector('.overlay[data-page-no="' + r.page_no + '"]');
      if (!overlay) return;
      const size = state.pageSizes[r.page_no];
      const box = document.createElement("div");
      box.className = "rbox " + (r.decision === "accepted" ? "on" : "off")
                    + (r.source === "human" ? " human" : "");
      box.style.left = r.nx0 * size.w + "px";
      box.style.top = r.ny0 * size.h + "px";
      box.style.width = (r.nx1 - r.nx0) * size.w + "px";
      box.style.height = (r.ny1 - r.ny0) * size.h + "px";
      box.title = (r.entity_type || "") + " " + (r.text_snippet || "");
      box.onclick = (e) => { e.stopPropagation(); toggle(r); };
      overlay.appendChild(box);
    });
  }

  function toggle(r) {
    r.decision = r.decision === "accepted" ? "rejected" : "accepted";
    drawBoxes();
    renderEntityList();
  }

  function enableDragToAdd(overlay, pageNo) {
    let startX, startY, ghost;
    overlay.addEventListener("mousedown", (e) => {
      const rect = overlay.getBoundingClientRect();
      startX = e.clientX - rect.left;
      startY = e.clientY - rect.top;
      ghost = document.createElement("div");
      ghost.className = "rbox on human";
      overlay.appendChild(ghost);
    });
    overlay.addEventListener("mousemove", (e) => {
      if (!ghost) return;
      const rect = overlay.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      ghost.style.left = Math.min(startX, x) + "px";
      ghost.style.top = Math.min(startY, y) + "px";
      ghost.style.width = Math.abs(x - startX) + "px";
      ghost.style.height = Math.abs(y - startY) + "px";
    });
    overlay.addEventListener("mouseup", (e) => {
      if (!ghost) return;
      const rect = overlay.getBoundingClientRect();
      const size = state.pageSizes[pageNo];
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      const nx0 = Math.min(startX, x) / size.w, ny0 = Math.min(startY, y) / size.h;
      const nx1 = Math.max(startX, x) / size.w, ny1 = Math.max(startY, y) / size.h;
      ghost.remove();
      ghost = null;
      if ((nx1 - nx0) * size.w < 4 || (ny1 - ny0) * size.h < 4) return; // te klein
      state.redactions.push({
        redaction_id: "temp_" + Date.now(),
        page_no: pageNo, nx0, ny0, nx1, ny1,
        entity_type: "HANDMATIG", source: "human", decision: "accepted",
      });
      drawBoxes();
      renderEntityList();
    });
  }

  function renderEntityList() {
    const groups = {};
    state.redactions.forEach((r) => {
      const k = r.entity_type || "OVERIG";
      (groups[k] = groups[k] || []).push(r);
    });
    const el = $("entity-list");
    el.innerHTML = "";
    Object.keys(groups).sort().forEach((type) => {
      const on = groups[type].filter((r) => r.decision === "accepted").length;
      const div = document.createElement("div");
      div.className = "entity-group";
      div.textContent = type + ": " + on + " / " + groups[type].length + " actief";
      el.appendChild(div);
    });
  }

  async function save() {
    const reviewer = $("reviewer").value || "onbekend";
    const decisions = state.redactions
      .filter((r) => !String(r.redaction_id).startsWith("temp_"))
      .map((r) => ({ redaction_id: r.redaction_id, decision: r.decision }));
    const added = state.redactions
      .filter((r) => String(r.redaction_id).startsWith("temp_"))
      .map((r) => ({ page_no: r.page_no, nx0: r.nx0, ny0: r.ny0, nx1: r.nx1, ny1: r.ny1 }));
    await fetch(api("redactions/" + state.caseId), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, decisions, added }),
    });
    await openCase({ case_id: state.caseId, filename: $("case-title").textContent });
  }

  async function approve() {
    if (!confirm("Case goedkeuren en definitief publiceren? De gekozen vlakken "
               + "worden echt en onomkeerbaar gelakt.")) return;
    await save();
    const reviewer = $("reviewer").value || "onbekend";
    const res = await fetch(api("approve/" + state.caseId), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer }),
    });
    const out = await res.json();
    alert("Gepubliceerd: " + out.redactions + " vlakken gelakt.");
    loadCases();
  }

  $("status-filter").addEventListener("change", loadCases);
  $("btn-save").addEventListener("click", save);
  $("btn-approve").addEventListener("click", approve);
  loadCases();
})();
