"""Review UI (spec §10): FastAPI + vanilla HTML/JS, single coder, review / blind / holdout-labeling modes.

Blind rule: for an encounter in blind mode the server never loads or transmits a prediction; the
predictions file is only read for encounters whose blind label has been submitted (or that are not
in the blind subset). Holdout-labeling mode never opens any predictions file at all and writes
labels encrypted to data/sealed/holdout_labels.enc.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from codeloop.ledger import utc_now
from codeloop.paths import Paths
from codeloop.review_ui.replay import build_blind_label, replay, status_of
from codeloop.review_ui.store import EventStore
from codeloop.schemas.encounter import Encounter, load_encounters_jsonl
from codeloop.schemas.event import REASONS, Event
from codeloop.schemas.label import LabelRecord
from codeloop.seal.crypto import decrypt_from_file, encrypt_to_file
from codeloop.util.jsonl import read_jsonl

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
.chip.supported{background:#dcfce7}.chip.unsupported{background:#fee2e2}
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
let DATA = null;
async function api(path, body){
  const r = await fetch(path, {method: body ? 'POST' : 'GET', headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
  if(!r.ok){ alert('error: ' + (await r.text())); throw new Error('api'); }
  return r.json();
}
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
function spanChips(ref, spans){
  return spans.map((s, i) => {
    const id = `${ref}#${i}`; const g = DATA.evidence_grades[id] || '';
    return `<span class="chip ${g}" title="${esc(s.text)}">${esc(s.source)} ${s.start}-${s.end} ${g ? '(' + g + ')' : ''}
      <button onclick="event.stopPropagation(); grade('${esc(ref)}','${esc(id)}','supported')">✓</button><button onclick="event.stopPropagation(); grade('${esc(ref)}','${esc(id)}','unsupported')">✗</button></span>`;
  }).join('');
}
async function post(ev){ await api('/api/event', ev); await load(); }
async function grade(ref, spanId, g){ await post({type: 'grade_evidence', field_ref: ref, span_id: spanId, grade: g}); }
async function gradeQuery(ref, g){ await post({type: 'grade_query', field_ref: ref, grade: g}); }
async function accept(ref){ await post({type: 'accept', field_ref: ref}); }
async function remove(ref, sel){ const reason = document.getElementById(sel).value; if(!reason){alert('choose a reason'); return;} await post({type: 'remove', field_ref: ref, reason}); }
async function editDx(code){
  const reason = document.getElementById('r-dx-'+code).value; if(DATA.mode==='review' && !reason){alert('choose a reason'); return;}
  const after = {code: document.getElementById('c-dx-'+code).value, status: document.getElementById('s-dx-'+code).value, first_listed: document.getElementById('f-dx-'+code).checked};
  await post({type: 'edit', field_ref: 'dx:'+code, after, reason: reason || null});
}
async function editLine(ref, key){
  const reason = document.getElementById('r-'+key).value; if(DATA.mode==='review' && !reason){alert('choose a reason'); return;}
  const after = {code: document.getElementById('c-'+key).value, modifiers: document.getElementById('m-'+key).value.split(',').map(s=>s.trim()).filter(Boolean),
    units: parseInt(document.getElementById('u-'+key).value || '1'), pointers: document.getElementById('p-'+key).value.split(',').map(s=>s.trim()).filter(Boolean)};
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
  await post({type: 'add', field_ref: 'line:'+code.toUpperCase(), after: {code, modifiers: document.getElementById('add-line-mods').value.split(',').map(s=>s.trim()).filter(Boolean), units: parseInt(document.getElementById('add-line-units').value||'1'), pointers: document.getElementById('add-line-ptr').value.split(',').map(s=>s.trim()).filter(Boolean)}, reason: reason || null});
}
async function approve(){ await api('/api/approve', {}); window.location = '/'; }
async function blindSubmit(){ if(!confirm('Submit the blind label? The draft will then be revealed.')) return; await api('/api/blind_submit', {}); await load(); }
function renderPackage(label, draft){
  const acc = new Set(DATA.accepted), touched = new Set(DATA.touched);
  let h = '<h3>Diagnoses</h3>';
  for(const d of label.diagnoses){
    const ref = 'dx:'+d.code; const spans = (draft && draft.spans[ref]) || [];
    const cls = acc.has(ref) ? 'accepted' : (touched.has(ref) ? 'touched' : '');
    h += `<div class="field ${cls}" onclick='highlight(${JSON.stringify(spans)})'><b>${esc(d.code)}</b> ${d.first_listed ? '<span class="chip">first-listed</span>' : ''} <span class="muted">${esc(d.status)}</span>
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
    const spans = (draft && draft.spans[ref]) || []; const cls = acc.has(ref) ? 'accepted' : (touched.has(ref) ? 'touched' : '');
    h += `<div class="field ${cls}" onclick='highlight(${JSON.stringify(spans)})'><b>${esc(l.code)}</b> mods [${esc(l.modifiers.join(','))}] units ${l.units} ptr [${esc(l.pointers.join(','))}]
      <div>${spanChips(ref, spans)}</div><div class="muted">${esc((draft && draft.rationales[ref]) || '')}</div>
      <div><input id="c-${key}" value="${esc(l.code)}" size="6"> mods <input id="m-${key}" value="${esc(l.modifiers.join(','))}" size="8"> units <input id="u-${key}" value="${l.units}" size="3"> ptr <input id="p-${key}" value="${esc(l.pointers.join(','))}" size="14"> ${reasonSelect('r-'+key)}
      ${DATA.mode==='review' ? `<button onclick="event.stopPropagation(); accept('${ref}')">Accept</button>` : ''}
      <button onclick="event.stopPropagation(); editLine('${ref}','${key}')">Edit</button><button onclick="event.stopPropagation(); remove('${ref}','r-${key}')">Remove</button></div></div>`;
  });
  h += `<div class="field"><b>Add line</b> <input id="add-line-code" placeholder="CPT/HCPCS" size="6"> mods <input id="add-line-mods" size="8"> units <input id="add-line-units" value="1" size="3"> ptr <input id="add-line-ptr" placeholder="codes, comma" size="14"> ${reasonSelect('r-add-line')} <button onclick="addLine()">Add</button></div>`;
  if(draft && draft.queries.length){
    h += '<h3>Provider queries</h3>';
    draft.queries.forEach((q, i) => { const ref = `query:${i}`; const g = DATA.query_grades[ref] || '';
      h += `<div class="field" onclick='highlight(${JSON.stringify(q.evidence)})'><span class="muted">${esc(q.field_ref)}</span> ${esc(q.question)} <b>${esc(g)}</b>
        <button onclick="event.stopPropagation(); gradeQuery('${ref}','warranted')">Warranted</button><button onclick="event.stopPropagation(); gradeQuery('${ref}','unwarranted')">Unwarranted</button></div>`; });
  }
  if(draft && draft.scrubber.length){ h += '<h3>Scrubber</h3>' + draft.scrubber.map(f => `<div class="muted">${esc(f.rule_id)} ${esc(f.severity)}: ${esc(f.message)}</div>`).join(''); }
  return h;
}
async function load(){
  DATA = await api('/api/encounter/' + encodeURIComponent(EID));
  document.getElementById('modebar').innerHTML = `mode: <b>${DATA.mode}</b> · status: ${DATA.status} · touches: ${DATA.touches}`;
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
window.addEventListener('load', async () => { if(typeof EID !== 'undefined'){ await api('/api/event', {type: 'open'}).catch(()=>{}); await load(); } });
"""


def _page(title: str, body: str, eid: str | None = None) -> str:
    js = _JS.replace("%REASONS%", json.dumps(list(REASONS)))
    head = f"<script>const EID = {json.dumps(eid)};</script>" if eid else ""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{_CSS}</style>{head}</head><body>{body}<script>{js}</script></body></html>"


class ReviewSession:
    """Server state: encounters, blind subset, lazy predictions, event store, holdout label sealing."""

    def __init__(
        self, paths: Paths, *, batch: str, version: str, coder_id: str, holdout_labeling: bool = False,
        passphrase: str | None = None, store_path: Path | None = None,
    ):
        self.paths, self.batch, self.version, self.coder_id = paths, batch, version, coder_id
        self.holdout = holdout_labeling
        self._passphrase = passphrase
        self._predictions: dict[str, dict[str, Any]] | None = None
        self.predictions_loaded_for: set[str] = set()
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

    def record(self, payload: dict[str, Any]) -> Event:
        eid = payload["encounter_id"]
        mode = self.mode(eid)
        ev = Event.model_validate({
            **payload, "ts": payload.get("ts") or utc_now(), "coder_id": self.coder_id, "batch": self.batch,
            "version": self.version, "mode": mode,
        })
        self.store.append(ev)
        return ev

    def blind_submit(self, eid: str) -> LabelRecord:
        events = self.events(eid)
        label = build_blind_label(events)
        ev = Event(ts=utc_now(), coder_id=self.coder_id, encounter_id=eid, batch=self.batch, version=self.version,
                   mode=self.mode(eid), type="blind_submit", after=label.model_dump(mode="json"))
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
            draft_view = {"spans": spans, "rationales": rationales, "queries": draft_pkg.get("provider_queries", []),
                          "scrubber": draft_pkg.get("scrubber", []), "data_gaps": draft_pkg.get("data_gaps", [])}
        return {
            "encounter_id": eid, "subset": enc.subset, "note_text": enc.note_text, "dialogue_text": enc.dialogue_text,
            "mode": mode, "status": status_of(events), "draft": draft_view, "label": label.model_dump(mode="json"),
            "touches": rec.touches if rec else 0,
            "accepted": [e.field_ref for e in events if e.type == "accept" and e.mode == "review"],
            "touched": [e.field_ref for e in events if e.type in ("edit", "add", "remove") and e.mode == "review"],
            "evidence_grades": rec.evidence_grades if rec else {}, "query_grades": rec.query_grades if rec else {},
            "blind_submitted": self.blind_done(eid),
        }


def create_review_app(session: ReviewSession) -> FastAPI:
    app = FastAPI(title="CodeLoop review")
    app.state.session = session

    @app.get("/", response_class=HTMLResponse)
    def queue() -> str:
        rows = []
        done = 0
        for eid in session.order:
            st = status_of(session.events(eid))
            done += st == "approved"
            rows.append(f"<tr><td><a href='/encounter/{html.escape(eid)}'>{html.escape(eid)}</a></td><td>{session.mode(eid)}</td><td>{st}</td></tr>")
        title = "Holdout blind labeling" if session.holdout else f"Review {session.version} · {session.batch}"
        body = (f"<header><strong>CodeLoop · {html.escape(title)}</strong><span>coder: {html.escape(session.coder_id)}</span>"
                f"<span>{done}/{len(session.order)} approved</span></header><main style='grid-template-columns:1fr'><div class='pane'>"
                "<table><tr><th>Encounter</th><th>Mode</th><th>Status</th></tr>" + "".join(rows) + "</table></div></main>")
        return _page(title, body)

    @app.get("/encounter/{eid}", response_class=HTMLResponse)
    def encounter(eid: str) -> str:
        if eid not in session.encounters:
            raise HTTPException(404, "not in this batch")
        enc = session.encounters[eid]
        body = (f"<header><a href='/'>← queue</a><strong>{html.escape(eid)}</strong><span>{enc.subset}</span>"
                f"<span id='modebar'></span><span>coder: {html.escape(session.coder_id)}</span></header><main>"
                f"<div class='pane'><h3>Note</h3><pre id='note'>{html.escape(enc.note_text)}</pre>"
                f"<details><summary>Transcript</summary><pre id='dialogue'>{html.escape(enc.dialogue_text)}</pre></details></div>"
                "<div class='pane' id='right'>loading…</div></main>")
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
        rec = session.blind_submit(eid)
        return JSONResponse({"ok": True, "blind_label": rec.blind_label.model_dump(mode="json") if rec.blind_label else None,
                             "mode": session.mode(eid)})

    @app.post("/api/approve")
    def api_approve(payload: dict[str, Any]) -> JSONResponse:
        eid = payload.get("encounter_id")
        if eid not in session.encounters:
            raise HTTPException(400, "unknown encounter")
        if session.mode(eid) != "review":
            raise HTTPException(400, "blind label must be submitted before approval")
        session.record({"encounter_id": eid, "type": "approve"})
        return JSONResponse({"ok": True})

    return app
