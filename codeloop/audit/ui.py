"""Minimal spot-check page for the CPC (FastAPI + vanilla HTML/JS, no build step).

Each reviewer sees only their own grades and progress (other reviewers' decisions are never displayed, to
avoid anchoring); the report merges all reviewers with the latest grade per flag winning.

Shows each sampled dev encounter (note, collapsible transcript) with the audit's flags; the CPC
confirms or denies each flag, may report a missed service, and marks the encounter done. Every
action is appended to runs/audit/spot_check_responses.jsonl. Holdout encounters are never loaded.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from codeloop.audit.responses import SpotCheckEvent, append_event, done_encounters, latest_grades, load_events
from codeloop.audit.run import load_results
from codeloop.audit.sample import load_spot_check_sample
from codeloop.audit.schema import CATEGORIES
from codeloop.paths import Paths
from codeloop.review_ui.auth import install_basic_auth
from codeloop.schemas.encounter import Encounter, load_encounters_jsonl

_CSS = """
body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1c1e21}
header{background:#1f2937;color:#fff;padding:.6rem 1rem;display:flex;gap:1rem;align-items:center}
header a{color:#fff}
main{display:grid;grid-template-columns:1fr 1fr;gap:1rem;padding:1rem}
.pane{background:#fff;border:1px solid #d9dde3;border-radius:6px;padding:1rem;overflow:auto;max-height:88vh}
pre{white-space:pre-wrap;font:13px/1.45 ui-monospace,Menlo,monospace}
.flag{border:1px solid #d9dde3;border-radius:6px;padding:.6rem;margin:.6rem 0}
.flag.confirm{border-color:#15803d;background:#f0fdf4}.flag.deny{border-color:#b91c1c;background:#fef2f2}
.cat{font-weight:600}.quote{background:#fef9c3;padding:.1rem .3rem}
button{padding:.35rem .7rem;margin-right:.3rem;border-radius:4px;border:1px solid #9aa3ad;background:#fff;cursor:pointer}
button.primary{background:#1f2937;color:#fff;border-color:#1f2937}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e5e7eb;padding:.35rem .5rem;text-align:left}
.done{color:#15803d;font-weight:600}
details{margin-top:1rem}
"""

_JS = """
async function post(body){
  const r = await fetch('/api/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){alert('save failed: '+(await r.text()));return false;}
  return true;
}
async function grade(eid, idx, decision){
  const c = document.getElementById('comment-'+idx).value;
  if(await post({encounter_id:eid,type:'grade',flag_index:idx,decision:decision,comment:c})){
    const el=document.getElementById('flag-'+idx); el.classList.remove('confirm','deny'); el.classList.add(decision);
    document.getElementById('state-'+idx).textContent=decision;
  }
}
async function missed(eid){
  const cat=document.getElementById('missed-cat').value, d=document.getElementById('missed-desc').value, q=document.getElementById('missed-quote').value;
  if(!d){alert('describe the service');return;}
  if(await post({encounter_id:eid,type:'missed',category:cat,description:d,evidence_quote:q})){
    const li=document.createElement('li'); li.textContent=cat+': '+d; document.getElementById('missed-list').appendChild(li);
    document.getElementById('missed-desc').value=''; document.getElementById('missed-quote').value='';
  }
}
async function done(eid){ if(await post({encounter_id:eid,type:'done'})){ window.location='/'; } }
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{_CSS}</style></head><body>{body}<script>{_JS}</script></body></html>"


def create_app(paths: Paths, reviewer: str, *, responses_path: Path | None = None, auth: bool = True) -> FastAPI:
    """`responses_path` redirects all writes/reads of spot-check responses (served deployments use a data volume)."""
    app = FastAPI(title="CodeLoop audit spot-check")
    app.state.auth = install_basic_auth(app) if auth else False
    store_path = responses_path
    encounters: dict[str, Encounter] = {e.id: e for e in load_encounters_jsonl(paths.dev_encounters)}
    results = load_results(paths)
    sample = load_spot_check_sample(paths)
    if not sample:
        raise RuntimeError("no spot-check sample; run `codeloop audit sample --n 30` first")
    order = [s["encounter_id"] for s in sample["encounters"]]
    arms = {s["encounter_id"]: s["arm"] for s in sample["encounters"]}

    @app.get("/", response_class=HTMLResponse)
    def queue() -> str:
        events = load_events(paths, store_path)
        done = done_encounters(events, reviewer)
        grades = latest_grades(events, reviewer)
        rows = []
        for eid in order:
            n_flags = len(results.get(eid, {"result": {"flags": []}})["result"]["flags"])
            graded = sum(1 for (e, _i) in grades if e == eid)
            state = "<span class='done'>done</span>" if eid in done else f"{graded}/{n_flags} graded"
            rows.append(
                f"<tr><td><a href='/encounter/{html.escape(eid)}'>{html.escape(eid)}</a></td><td>{arms[eid]}</td><td>{n_flags}</td><td>{state}</td></tr>"
            )
        body = (
            f"<header><strong>CodeLoop audit spot-check</strong><span>reviewer: {html.escape(reviewer)}</span>"
            f"<span>{len(done)}/{len(order)} done</span></header>"
            "<main style='grid-template-columns:1fr'><div class='pane'><table><tr><th>Encounter</th><th>Arm</th><th>Flags</th><th>Status</th></tr>"
            + "".join(rows)
            + "</table></div></main>"
        )
        return _page("Spot-check queue", body)

    @app.get("/encounter/{eid}", response_class=HTMLResponse)
    def encounter(eid: str) -> str:
        if eid not in arms or eid not in encounters:
            raise HTTPException(404, "not in the spot-check sample")
        enc = encounters[eid]
        rec = results.get(eid, {"result": {"flags": [], "patient": {}}, "flag_spans": []})
        grades = latest_grades(load_events(paths, store_path), reviewer)
        flags_html = []
        for i, f in enumerate(rec["result"]["flags"]):
            g = grades.get((eid, i))
            cls = f" {g.decision}" if g else ""
            facts = ", ".join(f"{k}={v}" for k, v in (f.get("facts") or {}).items() if v not in (None, "", False))
            flags_html.append(
                f"<div class='flag{cls}' id='flag-{i}'><div class='cat'>{i + 1}. {html.escape(f['category'])} "
                f"<small>({html.escape(f['confidence'])} confidence, {html.escape(f['evidence_source'])})</small> "
                f"<span id='state-{i}'>{html.escape(g.decision) if g else ''}</span></div>"
                f"<div>{html.escape(f['description'])}</div>"
                f"<div>Evidence: <span class='quote'>{html.escape(f['evidence_quote'])}</span></div>"
                + (f"<div><small>{html.escape(facts)}</small></div>" if facts else "")
                + f"<div style='margin-top:.4rem'><input id='comment-{i}' placeholder='comment (optional)' value='{html.escape(g.comment or '') if g else ''}' style='width:60%'> "
                f"<button onclick=\"grade('{html.escape(eid)}',{i},'confirm')\">Confirm</button>"
                f"<button onclick=\"grade('{html.escape(eid)}',{i},'deny')\">Deny</button></div></div>"
            )
        if not flags_html:
            flags_html.append("<p>No services flagged for this encounter.</p>")
        options = "".join(f"<option value='{c}'>{c}</option>" for c in CATEGORIES)
        patient = rec["result"].get("patient") or {}
        body = (
            f"<header><a href='/'>← queue</a><strong>{html.escape(eid)}</strong><span>{arms[eid]} arm · {enc.subset}</span>"
            f"<span>reviewer: {html.escape(reviewer)}</span></header><main>"
            f"<div class='pane'><h3>Note</h3><pre>{html.escape(enc.note_text)}</pre>"
            f"<details><summary>Transcript</summary><pre>{html.escape(enc.dialogue_text)}</pre></details></div>"
            f"<div class='pane'><h3>Audit flags</h3>{''.join(flags_html)}"
            f"<p><small>Patient facts from the audit: age {html.escape(str(patient.get('age_years')))}, sex {html.escape(str(patient.get('sex')))}</small></p>"
            f"<h3>Missed service?</h3><select id='missed-cat'>{options}</select> "
            f"<input id='missed-desc' placeholder='what was performed' style='width:40%'> "
            f"<input id='missed-quote' placeholder='evidence quote (optional)' style='width:30%'> "
            f"<button onclick=\"missed('{html.escape(eid)}')\">Add</button><ul id='missed-list'></ul>"
            f"<p><button class='primary' onclick=\"done('{html.escape(eid)}')\">Mark encounter done</button></p></div></main>"
        )
        return _page(f"Spot-check {eid}", body)

    @app.post("/api/event")
    def post_event(payload: dict[str, Any]) -> JSONResponse:
        if payload.get("encounter_id") not in arms:
            raise HTTPException(400, "encounter not in the spot-check sample")
        try:
            event = SpotCheckEvent.model_validate({**payload, "reviewer": reviewer})
            append_event(paths, event, store_path)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return JSONResponse({"ok": True})

    return app
