"""Review UI (spec §10): FastAPI + vanilla HTML/JS, single coder, review / blind / holdout-labeling modes.

Blind rule: for an encounter in blind mode the server never loads or transmits a prediction; the
predictions file is only read for encounters whose blind label has been submitted (or that are not
in the blind subset). Holdout-labeling mode never opens any predictions file at all and writes
labels encrypted to data/sealed/holdout_labels.enc.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from codeloop.ledger import utc_now
from codeloop.paths import Paths
from codeloop.review_ui.auth import install_basic_auth
from codeloop.review_ui.codeset import load_billable
from codeloop.review_ui.replay import (
    TOUCH_TYPES,
    apply_touch,
    build_blind_label,
    field_on_label,
    first_listed_problems,
    pointer_problems,
    replay,
    status_of,
)
from codeloop.review_ui.store import EventStore
from codeloop.schemas.encounter import Encounter, load_encounters_jsonl
from codeloop.schemas.event import REASONS, Event
from codeloop.schemas.label import LabelPackage, LabelRecord
from codeloop.seal.crypto import decrypt_from_file, encrypt_to_file
from codeloop.tools.validators import VALID_MODIFIERS
from codeloop.util.codes import looks_like_icd10cm, normalize_icd10cm
from codeloop.util.jsonl import read_jsonl

_LINE_CODE_RE = re.compile(r"^(?:[0-9]{4}[0-9A-Z]|[A-Z][0-9]{4})$")  # CPT (incl. category II/III, PLA) or HCPCS II shape
_MODIFIER_RE = re.compile(r"^[A-Z0-9]{2}$")


class Refused(ValueError):
    """An action the server will not store. The message is written for the coder and shown as is."""


_CSS = """
body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1c1e21}
header{background:#1f2937;color:#fff;padding:.5rem 1rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap}
header a{color:#fff}
main{display:grid;grid-template-columns:1fr 1fr;gap:1rem;padding:1rem}
.pane{background:#fff;border:1px solid #d9dde3;border-radius:6px;padding:1rem;overflow:auto;max-height:90vh}
pre{white-space:pre-wrap;font:13px/1.45 ui-monospace,Menlo,monospace}
mark{background:#fde68a}
.field{border:1px solid #d9dde3;border-radius:6px;padding:.5rem;margin:.5rem 0;cursor:pointer}
.field.accepted{border-color:#15803d;background:#f0fdf4}.field.touched{border-color:#b45309;background:#fffbeb}
.chip{display:inline-block;padding:.1rem .4rem;border:1px solid #9aa3ad;border-radius:10px;margin:.15rem;font-size:12px}
.chip.supported{background:#dcfce7}.chip.unsupported{background:#fee2e2}.chip.ungraded{background:#fff;border:1px dashed #b45309}
.bad{color:#b91c1c;font-weight:600}
button{padding:.3rem .6rem;margin:.15rem;border-radius:4px;border:1px solid #9aa3ad;background:#fff;cursor:pointer}
button.primary{background:#1f2937;color:#fff;border-color:#1f2937}
select,input{padding:.25rem;margin:.15rem}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e5e7eb;padding:.35rem .5rem;text-align:left}
.muted{color:#6b7280;font-size:12px}
details{margin-top:.8rem}
.banner{background:#fef3c7;border:1px solid #f59e0b;padding:.5rem;border-radius:6px;margin-bottom:.5rem}
"""

_JS = r"""
const REASONS = %REASONS%;
const KNOWN_MODIFIERS = %MODIFIERS%;
let DATA = null, SPANS = {};
async function api(path, body){
  const r = await fetch(path, {method: body ? 'POST' : 'GET', headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
  if(!r.ok){ const t = await r.text(); let msg = 'error: ' + t; try { const d = JSON.parse(t).detail; if(typeof d === 'string') msg = d; } catch(e) {} alert(msg); throw new Error('api'); }
  return r.json();
}
// Every POST is about the open encounter: the server rejects a body without encounter_id.
function send(path, body){ return api(path, {encounter_id: EID, ...body}); }
function esc(s){ return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function reasonSelect(id){ return `<select id="${id}"><option value="">reason…</option>${REASONS.map(r => `<option value="${r}">${r}</option>`).join('')}</select>`; }
function highlight(spans){
  const note = document.getElementById('note'), dlg = document.getElementById('dialogue');
  const render = (el, text, list) => {
    const sorted = list.filter(s => s.source === el.dataset.source).sort((a,b)=>a.start-b.start);
    let out = '', pos = 0;
    for(const s of sorted){ if(s.start < pos) continue; out += esc(text.slice(pos, s.start)) + '<mark>' + esc(text.slice(s.start, s.end)) + '</mark>'; pos = s.end; }
    out += esc(text.slice(pos)); el.innerHTML = out;
  };
  render(note, DATA.note_text, spans); render(dlg, DATA.dialogue_text, spans);
}
// Spans are looked up by ref, never inlined into an onclick attribute: passage text can hold quotes.
function show(ref){ highlight(SPANS[ref] || []); }
function spanChips(ref, spans){
  return spans.map((s, i) => {
    const id = `${ref}#${i}`; const g = DATA.evidence_grades[id] || '';
    return `<span class="chip ${g || 'ungraded'}" title="${esc(s.text)}">${esc(s.source)} ${s.start}-${s.end} (${g || 'not graded'})
      <button onclick="event.stopPropagation(); grade('${esc(ref)}','${esc(id)}','supported')">✓</button><button onclick="event.stopPropagation(); grade('${esc(ref)}','${esc(id)}','unsupported')">✗</button></span>`;
  }).join('');
}
async function post(ev){ await send('/api/event', ev); await load(); }
async function grade(ref, spanId, g){ await post({type: 'grade_evidence', field_ref: ref, span_id: spanId, grade: g}); }
async function gradeQuery(ref, g){ await post({type: 'grade_query', field_ref: ref, grade: g}); }
async function accept(ref){ await post({type: 'accept', field_ref: ref}); }
async function remove(ref, sel){ const reason = document.getElementById(sel).value; if(!reason){alert('choose a reason'); return;} await post({type: 'remove', field_ref: ref, reason}); }
async function editDx(code){
  const reason = document.getElementById('r-dx-'+code).value; if(DATA.mode==='review' && !reason){alert('choose a reason'); return;}
  const after = {code: document.getElementById('c-dx-'+code).value, status: document.getElementById('s-dx-'+code).value, first_listed: document.getElementById('f-dx-'+code).checked};
  await post({type: 'edit', field_ref: 'dx:'+code, after, reason: reason || null});
}
// A modifier outside the project's list is more often a typing slip than a choice, and a blind label is final.
function modifiersOk(mods){
  const odd = mods.map(m => m.toUpperCase()).filter(m => !KNOWN_MODIFIERS.includes(m));
  return !odd.length || confirm(`${odd.join(', ')} is not a modifier this project expects (${KNOWN_MODIFIERS.join(', ')}). Check the typing. Save it anyway?`);
}
async function editLine(ref, key){
  const reason = document.getElementById('r-'+key).value; if(DATA.mode==='review' && !reason){alert('choose a reason'); return;}
  const after = {code: document.getElementById('c-'+key).value, modifiers: document.getElementById('m-'+key).value.split(',').map(s=>s.trim()).filter(Boolean),
    units: parseInt(document.getElementById('u-'+key).value || '1'), pointers: document.getElementById('p-'+key).value.split(',').map(s=>s.trim()).filter(Boolean)};
  if(!modifiersOk(after.modifiers)) return;
  await post({type: 'edit', field_ref: ref, after, reason: reason || null});
}
async function addDx(){
  const reason = document.getElementById('r-add-dx').value; if(DATA.mode==='review' && !reason){alert('choose a reason'); return;}
  const code = document.getElementById('add-dx-code').value.trim(); if(!code){alert('code required'); return;}
  await post({type: 'add', field_ref: 'dx:'+code.toUpperCase().replace('.',''), after: {code, status: document.getElementById('add-dx-status').value, first_listed: document.getElementById('add-dx-first').checked}, reason: reason || null});
}
async function addLine(){
  const reason = document.getElementById('r-add-line').value; if(DATA.mode==='review' && !reason){alert('choose a reason'); return;}
  const code = document.getElementById('add-line-code').value.trim(); if(!code){alert('code required'); return;}
  const mods = document.getElementById('add-line-mods').value.split(',').map(s=>s.trim()).filter(Boolean); if(!modifiersOk(mods)) return;
  await post({type: 'add', field_ref: 'line:'+code.toUpperCase(), after: {code, modifiers: mods, units: parseInt(document.getElementById('add-line-units').value||'1'), pointers: document.getElementById('add-line-ptr').value.split(',').map(s=>s.trim()).filter(Boolean)}, reason: reason || null});
}
// A code typed into an Add box but never added would be lost without a word.
function typedNotAdded(){ return ['add-dx-code', 'add-line-code'].some(id => { const el = document.getElementById(id); return el && el.value.trim(); }); }
const NOT_ADDED = 'A code is typed in an Add box but was never added. Press Add, or clear the box.';
async function approve(){ if(typedNotAdded()){ alert(NOT_ADDED); return; } await send('/api/approve', {}); window.location = '/'; }
async function blindSubmit(){
  if(typedNotAdded()){ alert(NOT_ADDED); return; }
  if(!confirm(`Submit the blind label with ${DATA.label.diagnoses.length} diagnosis code(s) and ${DATA.label.lines.length} line(s)? This is final. The draft will then be revealed.`)) return;
  await send('/api/blind_submit', {}); await load();
}
function renderPackage(label, draft){
  const acc = new Set(DATA.accepted), touched = new Set(DATA.touched);
  SPANS = {};
  let h = '<h3>Diagnoses</h3>';
  for(const d of label.diagnoses){
    const ref = 'dx:'+d.code; const spans = (draft && draft.spans[ref]) || []; SPANS[ref] = spans;
    const cls = acc.has(ref) ? 'accepted' : (touched.has(ref) ? 'touched' : '');
    h += `<div class="field ${cls}" onclick="show('${esc(ref)}')"><b>${esc(d.code)}</b> ${d.first_listed ? '<span class="chip">first-listed</span>' : ''} <span class="muted">${esc(d.status)}</span>
      <div>${spanChips(ref, spans)}</div>
      <div class="muted">${esc((draft && draft.rationales[ref]) || '')}</div>
      <div><input id="c-dx-${esc(d.code)}" value="${esc(d.code)}" size="8"> <select id="s-dx-${esc(d.code)}"><option ${d.status==='active'?'selected':''}>active</option><option ${d.status==='historical'?'selected':''}>historical</option></select>
      <label><input type="checkbox" id="f-dx-${esc(d.code)}" ${d.first_listed?'checked':''}> first-listed</label> ${reasonSelect('r-dx-'+d.code)}
      ${DATA.mode==='review' ? `<button onclick="event.stopPropagation(); accept('${ref}')">Accept</button>` : ''}
      <button onclick="event.stopPropagation(); editDx('${esc(d.code)}')">Edit</button><button onclick="event.stopPropagation(); remove('${ref}','r-dx-${esc(d.code)}')">Remove</button></div></div>`;
  }
  h += `<div class="field"><b>Add diagnosis</b> <input id="add-dx-code" placeholder="ICD-10-CM" size="8"> <select id="add-dx-status"><option>active</option><option>historical</option></select> <label><input type="checkbox" id="add-dx-first"> first-listed</label> ${reasonSelect('r-add-dx')} <button onclick="addDx()">Add</button></div>`;
  h += '<h3>Lines</h3>';
  const seen = {};
  label.lines.forEach((l, i) => {
    const idx = seen[l.code] || 0; seen[l.code] = idx + 1; const ref = `line:${l.code}:${idx}`; const key = `line-${l.code}-${idx}`;
    const spans = (draft && draft.spans[ref]) || []; const cls = acc.has(ref) ? 'accepted' : (touched.has(ref) ? 'touched' : ''); SPANS[ref] = spans;
    const onPkg = p => { const c = String(p).toUpperCase().replace('.', ''); return /^[A-Z]$/.test(c) ? c.charCodeAt(0) - 65 < label.diagnoses.length : /^[0-9]+$/.test(c) ? c >= 1 && c <= label.diagnoses.length : label.diagnoses.some(d => d.code === c); };
    const ptrs = l.pointers.length ? l.pointers.map(p => onPkg(p) ? esc(p) : `<span class="bad" title="not a diagnosis on this package">${esc(p)} ⚠</span>`).join(',') : '<span class="bad">none ⚠</span>';
    h += `<div class="field ${cls}" onclick="show('${esc(ref)}')"><b>${esc(l.code)}</b> mods [${esc(l.modifiers.join(','))}] units ${l.units} ptr [${ptrs}]
      <div>${spanChips(ref, spans)}</div><div class="muted">${esc((draft && draft.rationales[ref]) || '')}</div>
      <div><input id="c-${key}" value="${esc(l.code)}" size="6"> mods <input id="m-${key}" value="${esc(l.modifiers.join(','))}" size="8"> units <input id="u-${key}" value="${l.units}" size="3"> ptr <input id="p-${key}" value="${esc(l.pointers.join(','))}" size="14"> ${reasonSelect('r-'+key)}
      ${DATA.mode==='review' ? `<button onclick="event.stopPropagation(); accept('${ref}')">Accept</button>` : ''}
      <button onclick="event.stopPropagation(); editLine('${ref}','${key}')">Edit</button><button onclick="event.stopPropagation(); remove('${ref}','r-${key}')">Remove</button></div></div>`;
  });
  h += `<div class="field"><b>Add line</b> <input id="add-line-code" placeholder="CPT/HCPCS" size="6"> mods <input id="add-line-mods" size="8"> units <input id="add-line-units" value="1" size="3"> ptr <input id="add-line-ptr" placeholder="codes, comma" size="14"> ${reasonSelect('r-add-line')} <button onclick="addLine()">Add</button></div>`;
  // Guidelines §4: passages on a field that was edited to another code or removed still get a grade,
  // and approval waits for them, so they stay on screen under their drafted ref.
  const orphans = draft ? Object.keys(draft.spans).filter(ref => !(ref in SPANS) && draft.spans[ref].length) : [];
  if(orphans.length){
    h += '<h3>Passages on edited or removed fields</h3>';
    for(const ref of orphans){ SPANS[ref] = draft.spans[ref];
      h += `<div class="field touched" onclick="show('${esc(ref)}')"><b>${esc(ref.split(':')[1])}</b> <span class="muted">as drafted</span><div>${spanChips(ref, draft.spans[ref])}</div></div>`; }
  }
  if(draft && draft.queries.length){
    h += '<h3>Provider queries</h3>';
    draft.queries.forEach((q, i) => { const ref = `query:${i}`; const g = DATA.query_grades[ref] || ''; SPANS[ref] = q.evidence;
      h += `<div class="field" onclick="show('${esc(ref)}')"><span class="muted">${esc(q.field_ref)}</span> ${esc(q.question)} <b>${esc(g)}</b>
        <button onclick="event.stopPropagation(); gradeQuery('${ref}','warranted')">Warranted</button><button onclick="event.stopPropagation(); gradeQuery('${ref}','unwarranted')">Unwarranted</button></div>`; });
  }
  if(draft && draft.scrubber.length){ h += '<h3>Scrubber</h3>' + draft.scrubber.map(f => `<div class="muted">${esc(f.rule_id)} ${esc(f.severity)}: ${esc(f.message)}</div>`).join(''); }
  return h;
}
async function load(){
  DATA = await api('/api/encounter/' + encodeURIComponent(EID));
  const pend = {fields: [], spans: [], queries: [], pointers: [], first_listed: [], ...(DATA.pending || {})};
  const structure = [...pend.pointers, ...pend.first_listed];
  const where = refs => refs.length ? ' (' + [...new Set(refs.map(x => esc(x.split('#')[0].split(':')[1])))].join(', ') + ')' : '';
  document.getElementById('modebar').innerHTML = `mode: <b>${DATA.mode}</b> · status: ${DATA.status} · touches: ${DATA.touches} · pending before approve: ${pend.fields.length} fields${where(pend.fields)}, ${pend.spans.length} passages${where(pend.spans)}, ${pend.queries.length} queries${structure.length ? ' · <span class="bad">' + esc(structure.join('; ')) + '</span>' : ''}`;
  document.getElementById('note').dataset.source = 'note'; document.getElementById('dialogue').dataset.source = 'dialogue';
  highlight([]);
  let right = '';
  if(DATA.mode === 'blind' || DATA.mode === 'holdout'){
    right = `<div class="banner">Blind coding: build the package from the note and transcript. No draft is available.</div>` + renderPackage(DATA.label, null) + `<p><button class="primary" onclick="blindSubmit()">Submit blind label</button></p>`;
  } else {
    right = renderPackage(DATA.label, DATA.draft) + `<p><button class="primary" onclick="approve()">Approve encounter</button></p>`;
  }
  document.getElementById('right').innerHTML = right;
}
window.addEventListener('load', async () => { if(typeof EID !== 'undefined'){ await send('/api/event', {type: 'open'}).catch(()=>{}); await load(); } });
"""


def _page(title: str, body: str, eid: str | None = None) -> str:
    js = _JS.replace("%REASONS%", json.dumps(list(REASONS))).replace("%MODIFIERS%", json.dumps(sorted(VALID_MODIFIERS)))
    head = f"<script>const EID = {json.dumps(eid)};</script>" if eid else ""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{_CSS}</style>{head}</head><body>{body}<script>{js}</script></body></html>"


class ReviewSession:
    """Server state: encounters, blind subset, lazy predictions, event store, holdout label sealing."""

    def __init__(
        self,
        paths: Paths,
        *,
        batch: str,
        version: str,
        coder_id: str,
        holdout_labeling: bool = False,
        passphrase: str | None = None,
        store_path: Path | None = None,
    ):
        self.paths, self.batch, self.version, self.coder_id = paths, batch, version, coder_id
        self.holdout = holdout_labeling
        self._passphrase = passphrase
        self._predictions: dict[str, dict[str, Any]] | None = None
        self.predictions_loaded_for: set[str] = set()
        self.codeset = load_billable()  # None when the list is absent: shape check only
        if holdout_labeling:
            if not passphrase:
                raise RuntimeError("holdout labeling requires CODELOOP_SEAL_KEY")
            raw = decrypt_from_file(paths.holdout_encounters_enc, passphrase).decode("utf-8")
            self.encounters = {e.id: e for e in (Encounter.model_validate_json(ln) for ln in raw.splitlines() if ln)}
            self.blind_ids = set(self.encounters)
            self.store = EventStore(store_path if store_path is not None else paths.sealed / "holdout_events.sqlite")
        else:
            from codeloop.versioning.freeze import load_dev_split

            split = load_dev_split(paths)
            ids = set(split["sets"][batch])
            self.encounters = {e.id: e for e in load_encounters_jsonl(paths.dev_encounters) if e.id in ids}
            self.blind_ids = set(split.get("blind", {}).get(batch, []))
            d = paths.review_dir(version, batch)
            self.store = EventStore(store_path if store_path is not None else d / "events.sqlite")
        self.order = sorted(self.encounters)

    # ---- state
    def events(self, eid: str) -> list[Event]:
        return self.store.for_encounter(eid)

    def blind_done(self, eid: str) -> bool:
        return any(e.type == "blind_submit" for e in self.events(eid))

    def mode(self, eid: str) -> str:
        if self.holdout:
            return "holdout"
        if eid in self.blind_ids and not self.blind_done(eid):
            return "blind"
        return "review"

    def draft(self, eid: str) -> dict[str, Any] | None:
        """Only ever touches the predictions file for encounters in review mode."""
        if self.mode(eid) != "review":
            return None
        if self._predictions is None:
            path = self.paths.runs / self.version / self.batch / "predictions.jsonl"
            self._predictions = {r["encounter_id"]: r for r in read_jsonl(path)} if path.exists() else {}
        self.predictions_loaded_for.add(eid)
        return self._predictions.get(eid)

    def current_label(self, eid: str) -> LabelPackage:
        events = self.events(eid)
        if self.mode(eid) == "review":
            return replay(eid, self.coder_id, self.draft(eid), events).label
        return build_blind_label(events)

    def check_touch(self, ev: Event) -> None:
        """Refuse an edit/add/remove that cannot mean what the coder intends. The store is append-only and labels
        are rebuilt by replaying it, so a bad event can never be taken back: it is dry-run on a copy of the current
        package first, and refused when it fails, changes nothing, or carries a blank or misshapen code."""
        ref = ev.field_ref or ""
        kind = ref.split(":")[0]
        if kind not in ("dx", "line", "first_listed"):
            raise Refused(f"Unknown field {ref!r}. Reload the page and try again.")
        after = ev.after or {}
        if ev.type == "add" or (ev.type == "edit" and "code" in after):
            code = str(after.get("code") or "").strip()
            if not code:
                raise Refused("The code box is empty. Type the code, then press the button again.")
            if kind == "line" and not _LINE_CODE_RE.match(code.upper()):
                raise Refused(f"{code!r} is not shaped like a CPT or HCPCS code (five characters). Check the typing.")
            if kind != "line" and not looks_like_icd10cm(code):
                raise Refused(f"{code!r} is not shaped like an ICD-10-CM code. Check the typing.")
        odd = [m for m in (after.get("modifiers") or []) if not _MODIFIER_RE.match(str(m).strip().upper())]
        if kind == "line" and odd:
            raise Refused(f"Modifiers are two characters each, separated by commas; {odd[0]!r} is not. Check the typing.")
        label = self.current_label(ev.encounter_id)
        if ev.type in ("edit", "remove") and not field_on_label(label, ref):
            raise Refused("That field is not on the package any more. Reload the page.")
        if kind == "dx" and "code" in after and (ev.type == "add" or normalize_icd10cm(str(after["code"])) != ref.split(":")[1]):
            self.check_billable(str(after["code"]).strip())  # only a code the coder typed, never one merely kept
        if kind != "line" and "code" in after:
            new_code, on_label = normalize_icd10cm(str(after["code"])), {d.code for d in label.diagnoses}
            if kind == "first_listed" and new_code not in on_label:
                raise Refused(f"{after['code']} is not on the package, so it cannot be first-listed.")
            if kind == "dx" and new_code in on_label and (ev.type == "add" or new_code != ref.split(":")[1]):
                raise Refused(f"{after['code']} is already on the package.")
        try:
            _, changed = apply_touch(label.model_copy(deep=True), ev)
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
            raise Refused(f"That value cannot be saved ({problems}).") from e
        if not changed:
            raise Refused(
                "Nothing changed, so nothing was saved. Edit saves what is in the boxes: change the value first, then "
                "choose the reason and press Edit. If the field is right as drafted, press Accept."
            )

    def check_billable(self, code: str) -> None:
        if self.codeset is None or self.codeset.is_billable(code):
            return
        release = self.codeset.release or "current"
        if self.codeset.has_more_specific(code):
            raise Refused(
                f"{code} is not a billable {release} ICD-10-CM code: more specific codes exist under it. "
                "Enter the full code."
            )
        raise Refused(f"{code} is not in the {release} ICD-10-CM code set. Check the typing.")

    def record(self, payload: dict[str, Any]) -> Event:
        eid = payload["encounter_id"]
        mode = self.mode(eid)
        ev = Event.model_validate(
            {
                **payload,
                "ts": payload.get("ts") or utc_now(),
                "coder_id": self.coder_id,
                "batch": self.batch,
                "version": self.version,
                "mode": mode,
            }
        )
        if ev.type in TOUCH_TYPES:
            self.check_touch(ev)
        self.store.append(ev)
        return ev

    def blind_submit(self, eid: str) -> LabelRecord:
        events = self.events(eid)
        label = build_blind_label(events)
        if not label.diagnoses:  # final and unrepeatable once the draft is revealed, so never by accident
            raise Refused(
                "The blind label has no diagnoses yet, so it was not submitted. Type each code, press Add, check "
                "the list, then submit. Submitting is final."
            )
        problems = pointer_problems(label)
        if problems:
            raise Refused("Not submitted: " + "; ".join(problems) + ". Fix the line's pointer box (Edit), then submit.")
        problems = first_listed_problems(label)
        if problems:
            raise Refused(
                "Not submitted: " + "; ".join(problems) + ". Tick first-listed on the condition chiefly responsible "
                "for the visit and press Edit, then submit."
            )
        ev = Event(
            ts=utc_now(),
            coder_id=self.coder_id,
            encounter_id=eid,
            batch=self.batch,
            version=self.version,
            mode=self.mode(eid),
            type="blind_submit",
            after=label.model_dump(mode="json"),
        )
        self.store.append(ev)
        record = LabelRecord(encounter_id=eid, coder_id=self.coder_id, label=label, blind_label=label)
        if self.holdout:
            self._seal_holdout_label(record)
        return record

    def _seal_holdout_label(self, record: LabelRecord) -> None:
        assert self._passphrase
        existing: dict[str, dict[str, Any]] = {}
        p = self.paths.holdout_labels_enc
        if p.exists():
            raw = decrypt_from_file(p, self._passphrase).decode("utf-8")
            for ln in raw.splitlines():
                if ln:
                    d = json.loads(ln)
                    existing[f"{d['coder_id']}:{d['encounter_id']}"] = d
        existing[f"{record.coder_id}:{record.encounter_id}"] = record.model_dump(mode="json")
        plaintext = "".join(json.dumps(existing[k], sort_keys=True) + "\n" for k in sorted(existing)).encode("utf-8")
        encrypt_to_file(plaintext, p, self._passphrase, label="holdout_labels")

    def pending(self, eid: str) -> dict[str, list[str]]:
        """What still needs a decision before approval (coder guidelines §4): every drafted field accepted,
        edited or removed; every cited passage graded; every provider query graded."""
        events = self.events(eid)
        draft = self.draft(eid) or {}
        decided = {
            e.field_ref for e in events if e.mode == "review" and e.type in ("accept", "edit", "remove") and e.field_ref
        }
        fields: list[str] = [f"dx:{d['code']}" for d in draft.get("diagnoses", [])]
        spans: list[str] = [
            f"dx:{d['code']}#{i}" for d in draft.get("diagnoses", []) for i, _ in enumerate(d.get("evidence", []))
        ]
        seen: dict[str, int] = {}
        for ln in draft.get("lines", []):
            idx = seen.get(ln["code"], 0)
            seen[ln["code"]] = idx + 1
            fields.append(f"line:{ln['code']}:{idx}")
            spans.extend(f"line:{ln['code']}:{idx}#{i}" for i, _ in enumerate(ln.get("evidence", [])))
        queries = [f"query:{i}" for i in range(len(draft.get("provider_queries", [])))]
        rec = replay(eid, self.coder_id, draft, events)
        return {
            "fields": [f for f in fields if f not in decided],
            "spans": [x for x in spans if x not in rec.evidence_grades],
            "queries": [q for q in queries if q not in rec.query_grades],
            "pointers": pointer_problems(rec.label),
            "first_listed": first_listed_problems(rec.label),
        }

    def state(self, eid: str) -> dict[str, Any]:
        enc = self.encounters[eid]
        events = self.events(eid)
        mode = self.mode(eid)
        draft_pkg = self.draft(eid)
        if mode == "review":
            rec = replay(eid, self.coder_id, draft_pkg, events)
            label = rec.label
        else:
            rec = None
            label = build_blind_label(events)
        draft_view = None
        if draft_pkg is not None:
            spans: dict[str, list[dict[str, Any]]] = {}
            rationales: dict[str, str] = {}
            for d in draft_pkg.get("diagnoses", []):
                spans[f"dx:{d['code']}"] = d.get("evidence", [])
                rationales[f"dx:{d['code']}"] = d.get("rationale", "")
            seen: dict[str, int] = {}
            for ln in draft_pkg.get("lines", []):
                idx = seen.get(ln["code"], 0)
                seen[ln["code"]] = idx + 1
                spans[f"line:{ln['code']}:{idx}"] = ln.get("evidence", [])
                rationales[f"line:{ln['code']}:{idx}"] = ln.get("rationale", "")
            draft_view = {
                "spans": spans,
                "rationales": rationales,
                "queries": draft_pkg.get("provider_queries", []),
                "scrubber": draft_pkg.get("scrubber", []),
                "data_gaps": draft_pkg.get("data_gaps", []),
            }
        return {
            "encounter_id": eid,
            "subset": enc.subset,
            "note_text": enc.note_text,
            "dialogue_text": enc.dialogue_text,
            "mode": mode,
            "status": status_of(events),
            "draft": draft_view,
            "label": label.model_dump(mode="json"),
            "touches": rec.touches if rec else 0,
            "accepted": [e.field_ref for e in events if e.type == "accept" and e.mode == "review"],
            "touched": [e.field_ref for e in events if e.type in ("edit", "add", "remove") and e.mode == "review"],
            "evidence_grades": rec.evidence_grades if rec else {},
            "query_grades": rec.query_grades if rec else {},
            "blind_submitted": self.blind_done(eid),
            "pending": self.pending(eid)
            if mode == "review"
            else {
                "fields": [], "spans": [], "queries": [],
                "pointers": pointer_problems(label), "first_listed": first_listed_problems(label),
            },
        }


def _not_ready(pending: dict[str, list[str]]) -> str:
    """The approve refusal, naming what is missing: an ungraded passage on a card that is already accepted is easy
    to overlook, and a bare count sent a coder hunting through the wrong fields."""

    def codes(refs: list[str]) -> str:
        counts: dict[str, int] = {}
        for r in refs:
            code = r.split("#")[0].split(":")[1]
            counts[code] = counts.get(code, 0) + 1
        return ", ".join(f"{c} x{n}" if n > 1 else c for c, n in counts.items())

    parts = []
    if pending["fields"]:
        parts.append(f"{len(pending['fields'])} field(s) need Accept, Edit or Remove ({codes(pending['fields'])})")
    if pending["spans"]:
        parts.append(f"{len(pending['spans'])} passage(s) not graded, on {codes(pending['spans'])}")
    if pending["queries"]:
        numbers = ", ".join(str(int(q.split(":")[1]) + 1) for q in pending["queries"])
        parts.append(f"{len(pending['queries'])} provider query(ies) not graded (no. {numbers})")
    if pending.get("pointers"):
        parts.append("; ".join(pending["pointers"]) + " (fix the line's pointer box with Edit)")
    if pending.get("first_listed"):
        parts.append("; ".join(pending["first_listed"]) + " (tick first-listed on one diagnosis and press Edit)")
    return "not ready to approve: " + "; ".join(parts) + "."


def create_review_app(session: ReviewSession, *, auth: bool = True) -> FastAPI:
    app = FastAPI(title="CodeLoop review")
    app.state.session = session
    app.state.auth = install_basic_auth(app) if auth else False

    @app.get("/", response_class=HTMLResponse)
    def queue() -> str:
        rows = []
        done = 0
        for eid in session.order:
            st = status_of(session.events(eid))
            done += st == "approved"
            rows.append(
                f"<tr><td><a href='/encounter/{html.escape(eid)}'>{html.escape(eid)}</a></td><td>{session.mode(eid)}</td><td>{st}</td></tr>"
            )
        title = "Holdout blind labeling" if session.holdout else f"Review {session.version} · {session.batch}"
        body = (
            f"<header><strong>CodeLoop · {html.escape(title)}</strong><span>coder: {html.escape(session.coder_id)}</span>"
            f"<span>{done}/{len(session.order)} approved</span></header><main style='grid-template-columns:1fr'><div class='pane'>"
            "<table><tr><th>Encounter</th><th>Mode</th><th>Status</th></tr>" + "".join(rows) + "</table></div></main>"
        )
        return _page(title, body)

    @app.get("/encounter/{eid}", response_class=HTMLResponse)
    def encounter(eid: str) -> str:
        if eid not in session.encounters:
            raise HTTPException(404, "not in this batch")
        enc = session.encounters[eid]
        body = (
            f"<header><a href='/'>← queue</a><strong>{html.escape(eid)}</strong><span>{enc.subset}</span>"
            f"<span id='modebar'></span><span>coder: {html.escape(session.coder_id)}</span></header><main>"
            f"<div class='pane'><h3>Note</h3><pre id='note'>{html.escape(enc.note_text)}</pre>"
            f"<details><summary>Transcript</summary><pre id='dialogue'>{html.escape(enc.dialogue_text)}</pre></details></div>"
            "<div class='pane' id='right'>loading…</div></main>"
        )
        return _page(f"{eid}", body, eid=eid)

    @app.get("/api/encounter/{eid}")
    def api_encounter(eid: str) -> JSONResponse:
        if eid not in session.encounters:
            raise HTTPException(404, "not in this batch")
        return JSONResponse(session.state(eid))

    @app.post("/api/event")
    def api_event(payload: dict[str, Any]) -> JSONResponse:
        eid = payload.get("encounter_id") or payload.get("eid")
        if eid not in session.encounters:
            raise HTTPException(400, "unknown encounter")
        payload["encounter_id"] = eid
        try:
            ev = session.record(payload)
        except Refused as e:
            raise HTTPException(400, str(e)) from e
        except (ValidationError, ValueError) as e:
            raise HTTPException(400, f"invalid event: {e}") from e
        return JSONResponse({"ok": True, "type": ev.type, "mode": ev.mode})

    @app.post("/api/blind_submit")
    def api_blind_submit(payload: dict[str, Any]) -> JSONResponse:
        eid = payload.get("encounter_id")
        if eid not in session.encounters:
            raise HTTPException(400, "unknown encounter")
        if session.mode(eid) not in ("blind", "holdout"):
            raise HTTPException(400, "encounter is not in blind mode")
        try:
            rec = session.blind_submit(eid)
        except Refused as e:
            raise HTTPException(400, str(e)) from e
        return JSONResponse(
            {
                "ok": True,
                "blind_label": rec.blind_label.model_dump(mode="json") if rec.blind_label else None,
                "mode": session.mode(eid),
            }
        )

    @app.post("/api/approve")
    def api_approve(payload: dict[str, Any]) -> JSONResponse:
        eid = payload.get("encounter_id")
        if eid not in session.encounters:
            raise HTTPException(400, "unknown encounter")
        if session.mode(eid) != "review":
            raise HTTPException(400, "blind label must be submitted before approval")
        pending = session.pending(eid)
        if any(pending.values()):
            raise HTTPException(400, _not_ready(pending))
        session.record({"encounter_id": eid, "type": "approve"})
        return JSONResponse({"ok": True})

    return app
