document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("report-tbody");
  if (!tbody) return;
  const rows = [...tbody.querySelectorAll("tr")];
  const modal = document.getElementById("ticket-modal");
  let page = 1, timer;
  const pageSize = 10;
  const colors = {"Abierto":"#ffca37","En proceso":"#2e8cf7","Resuelto":"#10b981","Cerrado":"#8b95a5","Vencido":"#f04452"};
  const norm = s => (s || "").toLocaleLowerCase("es").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  function notify(msg) {
    const toast = document.getElementById("toast");
    toast.textContent = msg; toast.classList.add("show");
    clearTimeout(timer); timer = setTimeout(() => toast.classList.remove("show"), 2600);
  }
  function statusOf(r) {
    const status = r.dataset.status || "";
    const deadline = r.dataset.deadline;
    const today = new Date().toISOString().slice(0,10);
    if (!["Resuelto","Cerrado"].includes(status) && deadline && deadline < today) return "Vencido";
    return status;
  }
  function filtered() {
    const from = document.getElementById("date-from").value, to = document.getElementById("date-to").value;
    const area = document.getElementById("area-filter").value, cat = document.getElementById("category-filter").value;
    const pri = document.getElementById("priority-filter").value, status = document.getElementById("status-filter").value;
    const tech = document.getElementById("technician-filter").value, q = norm(document.getElementById("table-search").value.trim());
    return rows.filter(r => {
      const haystack = norm(`${r.dataset.id} ${r.dataset.subject} ${r.dataset.requester} ${r.dataset.technician}`);
      return (!from || r.dataset.created >= from) && (!to || r.dataset.created <= to) &&
        (!area || r.dataset.area === area) && (!cat || r.dataset.category === cat) &&
        (!pri || r.dataset.priority === pri) && (!status || statusOf(r) === status) &&
        (!tech || r.dataset.technician === tech) && (!q || haystack.includes(q));
    });
  }
  function charts(found) {
    const statuses = ["Abierto","En proceso","Resuelto","Cerrado","Vencido"], total = found.length, denom = total || 1;
    const counts = statuses.map(s => found.filter(r => statusOf(r) === s).length);
    document.getElementById("total-count").textContent = total;
    document.getElementById("resolved-count").textContent = counts[2];
    document.getElementById("progress-count").textContent = counts[1];
    document.getElementById("pending-count").textContent = counts[0] + counts[4];
    document.getElementById("donut-total").textContent = total;
    let angle = 0;
    const segments = statuses.map((s,i) => { const next = angle + counts[i]/denom*100; const part = `${colors[s]} ${angle}% ${next}%`; angle = next; return part; });
    document.getElementById("status-donut").style.background = `conic-gradient(${segments.join(",")})`;
    document.getElementById("status-legend").innerHTML = statuses.map((s,i) =>
      `<li><i style="background:${colors[s]}"></i><span>${s}</span><b>${counts[i]} <small>(${Math.round(counts[i]/denom*100)}%)</small></b></li>`).join("");
    const priorities = [...new Set(rows.map(r => r.dataset.priority).filter(Boolean))];
    const pcounts = priorities.map(p => found.filter(r => r.dataset.priority === p).length), maxP = Math.max(1,...pcounts);
    const pcols = ["#f04452","#ffb91e","#14b88a","#2e8cf7"];
    document.getElementById("priority-chart").innerHTML = priorities.map((p,i) =>
      `<div class="bar-item"><b>${pcounts[i]}</b><div class="bar" style="height:${Math.max(4,pcounts[i]/maxP*88)}px;background:${pcols[i%pcols.length]}"></div><label>${p}</label></div>`).join("");
    const categories = [...new Set(rows.map(r => r.dataset.category).filter(Boolean))];
    const ccounts = categories.map(c => found.filter(r => r.dataset.category === c).length), maxC = Math.max(1,...ccounts);
    document.getElementById("category-chart").innerHTML = categories.map((c,i) =>
      `<div class="category-row"><span>${c}</span><div class="category-track"><div class="category-fill" style="width:${ccounts[i]/maxC*100}%"></div></div><b>${ccounts[i]} (${Math.round(ccounts[i]/denom*100)}%)</b></div>`).join("");
  }
  function render() {
    const found = filtered(), pages = Math.max(1,Math.ceil(found.length/pageSize));
    page = Math.min(page,pages);
    const start = (page-1)*pageSize, visible = new Set(found.slice(start,start+pageSize));
    rows.forEach(r => r.hidden = !visible.has(r));
    document.getElementById("results-label").textContent = found.length ?
      `Mostrando ${start+1}–${Math.min(start+pageSize,found.length)} de ${found.length} registros` : "No hay resultados para estos filtros";
    document.getElementById("empty-state").hidden = found.length > 0;
    document.querySelector(".table-wrap").hidden = found.length === 0;
    document.querySelectorAll(".page-number").forEach(b => { b.hidden = Number(b.dataset.page)>pages; b.classList.toggle("active",Number(b.dataset.page)===page); });
    document.getElementById("prev-page").disabled = page <= 1;
    document.getElementById("next-page").disabled = page >= pages;
    charts(found);
  }
  function clearFilters() {
    ["area-filter","category-filter","priority-filter","status-filter","technician-filter"].forEach(id => document.getElementById(id).value = "");
    document.getElementById("date-from").value = ""; document.getElementById("date-to").value = "";
    document.getElementById("table-search").value = ""; page = 1; render();
    document.getElementById("filter-message").textContent = "Se muestran todos los tickets de tu empresa.";
    notify("Filtros restablecidos.");
  }
  document.getElementById("generate-report").addEventListener("click", () => {
    const a = document.getElementById("date-from").value, b = document.getElementById("date-to").value;
    if (a && b && a > b) return notify("La fecha inicial no puede ser posterior a la final.");
    page = 1; render(); document.getElementById("filter-message").textContent = "Reporte actualizado con los filtros seleccionados."; notify("Reporte actualizado.");
  });
  document.getElementById("clear-filters").addEventListener("click",clearFilters);
  document.getElementById("empty-clear").addEventListener("click",clearFilters);
  document.getElementById("table-search").addEventListener("input",() => {page=1;render();});
  // Módulo 6: exportación real en el servidor (openpyxl / ReportLab) con los filtros elegidos
  function exportar(formato) {
    const p = new URLSearchParams();
    const val = id => document.getElementById(id).value;
    [["desde","date-from"],["hasta","date-to"],["area","area-filter"],["categoria","category-filter"],
     ["prioridad","priority-filter"],["estado","status-filter"],["tecnico","technician-filter"],["q","table-search"]]
      .forEach(([k,id]) => { const v = val(id).trim(); if (v) p.set(k, v); });
    notify(`Generando ${formato === "excel" ? "Excel" : "PDF"} con ${filtered().length} registro(s)...`);
    window.location.href = `/reportes/exportar/${formato}?${p.toString()}`;
  }
  document.getElementById("export-csv").addEventListener("click", () => exportar("excel"));
  document.getElementById("export-print").addEventListener("click", () => exportar("pdf"));
  tbody.addEventListener("click",e=>{
    const button=e.target.closest(".view"); if(!button)return; const r=button.closest("tr");
    document.getElementById("modal-title").textContent=`Detalle de ${r.dataset.id}`;
    document.getElementById("modal-description").textContent=[
      `Asunto: ${r.dataset.subject}`,`Solicitante: ${r.dataset.requester}`,`Área: ${r.dataset.area}`,
      `Categoría: ${r.dataset.category}`,`Prioridad: ${r.dataset.priority}`,`Estado: ${statusOf(r)}`,
      `Técnico: ${r.dataset.technician}`,`Fecha de creación: ${r.dataset.created}`,
      `Fecha límite: ${r.dataset.deadline||"No definida"}`,`Última actualización: ${r.dataset.updated||"Sin dato"}`
    ].join("\n"); modal.hidden=false;
  });
  const close=()=>modal.hidden=true;
  document.getElementById("modal-close").addEventListener("click",close);
  document.getElementById("modal-ok").addEventListener("click",close);
  modal.addEventListener("click",e=>{if(e.target===modal)close();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")close();});
  document.getElementById("prev-page").addEventListener("click",()=>{if(page>1){page--;render();}});
  document.getElementById("next-page").addEventListener("click",()=>{if(page<Math.ceil(filtered().length/pageSize)){page++;render();}});
  document.querySelectorAll(".page-number").forEach(b=>b.addEventListener("click",()=>{page=Number(b.dataset.page);render();}));
  // (los botones de notificaciones y perfil los maneja base.html; aquí no existen)
  document.getElementById("global-search")?.addEventListener("keydown",e=>{
    if(e.key==="Enter"&&e.target.value.trim()){document.getElementById("table-search").value=e.target.value.trim();page=1;render();notify("Búsqueda aplicada.");}
  });
  render();
});
