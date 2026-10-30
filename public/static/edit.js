const $ = s => document.querySelector(s), Q = window.Q;
const fmt = n => (Math.round(n * 100) / 100).toLocaleString('fr-FR');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const total = () => Q.items.reduce((s, r) => s + (+r.q || 0) * (+r.p || 0), 0);
const tt = () => $('#tot').textContent = fmt(total()) + ' ' + Q.cur;
let timer;
function save() {
  $('#st').textContent = 'Enregistrement…'; clearTimeout(timer);
  timer = setTimeout(() => fetch(window.SAVE, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Q)})
    .then(r => $('#st').textContent = r.ok ? 'Enregistré ✓' : 'Erreur')
    .catch(() => $('#st').textContent = 'Erreur réseau'), 500);
}
function draw() {
  const sec = (t, l) => `<tr class="sec"><td colspan="4">${l}</td></tr>` + Q.items.map((r, i) => r.t !== t ? '' :
    `<tr><td><input data-i="${i}" data-k="d" value="${esc(r.d)}" placeholder="Désignation"></td>
    <td class="q"><input type="number" min="0" data-i="${i}" data-k="q" value="${r.q}"></td>
    <td class="p"><input type="number" min="0" data-i="${i}" data-k="p" value="${r.p}"></td>
    <td class="n" id="m${i}">${fmt(r.q * r.p)}</td>
    <td class="no-print nb"><button class="x" data-rm="${i}">✕</button></td></tr>`).join('') +
    `<tr class="no-print"><td colspan="4" class="nb"><button data-add="${t}">+ Ajouter une ligne</button></td></tr>`;
  $('#tb').innerHTML = sec('m', 'MATÉRIEL') + sec('o', 'AUTRES INFORMATIONS / PRESTATIONS') +
    '<tr class="tot"><td colspan="3" style="text-align:right">TOTAL</td><td class="n" id="tot"></td></tr>';
  tt();
}
document.addEventListener('input', e => {
  const d = e.target.dataset;
  if (d.i !== undefined) { Q.items[d.i][d.k] = e.target.value; const r = Q.items[d.i];
    $('#m' + d.i).textContent = fmt((+r.q || 0) * (+r.p || 0)); }
  else if (d.f) Q[d.f] = e.target.value; else return;
  tt(); save();
});
document.addEventListener('click', e => {
  const d = e.target.dataset;
  if (d.add) { Q.items.push({t: d.add, d: '', q: 1, p: 0}); draw(); save(); }
  if (d.rm !== undefined) { Q.items.splice(+d.rm, 1); draw(); save(); }
});
draw();
