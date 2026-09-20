"""Browser-level test of the review UI: the page's own JavaScript against the real server. Opt-in: `make ui-e2e`.

The JSON API tests post hand-written bodies, so they cannot notice the page sending something else (it once sent
every POST without encounter_id and nothing a coder did was saved). This drives headless Chrome through the coder's
flows on the synthetic corpus, served by the deploy entrypoint with basic auth on, and then replays the stored
events the way `labels build` does. Skipped unless Playwright and a browser it can launch are installed, so plain
`uv run pytest` and CI never need them. Synthetic text only.
"""

import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from codeloop.review_ui.replay import replay  # noqa: E402
from codeloop.review_ui.serve import ServeSettings, build_app  # noqa: E402
from codeloop.review_ui.store import EventStore  # noqa: E402
from codeloop.util.jsonl import write_jsonl  # noqa: E402
from tests.test_review_ui import _repo  # noqa: E402

AUTH = {"username": "cpc", "password": "pw-123456"}
CODER = "cpc1"
ORPHANS = "Passages on edited or removed fields"


def _span(start, end, text):
    return {"source": "note", "start": start, "end": end, "text": text, "sha256": "x"}


def _draft(eid):
    # passage text with an apostrophe and a double quote: both used to break the click-to-highlight handler
    return {
        "encounter_id": eid, "version": "dev", "run_id": "r",
        "diagnoses": [
            {"code": "M1711", "status": "active", "first_listed": True, "rationale": "synthetic",
             "evidence": [_span(0, 5, 'synthetic patient\'s "quoted" passage')]},
            {"code": "E119", "status": "active", "first_listed": False, "rationale": "synthetic",
             "evidence": [_span(6, 12, "plain passage")]},
        ],
        "lines": [{"code": "73562", "modifiers": ["26"], "units": 1, "pointers": ["M1711"], "module": "core_lines",
                   "evidence": [_span(13, 18, "line's passage")], "rationale": ""}],
        "provider_queries": [{"field_ref": "dx:M1711:laterality", "question": "synthetic question?",
                              "evidence": [_span(0, 3, "q's passage")], "suggested_value": None}],
        "data_gaps": [], "scrubber": [],
        "compliance": {"policy": "note_only", "checked": True, "passed": True, "issues": [], "downgraded_fields": []},
    }


@pytest.fixture
def served(tmp_path, monkeypatch):
    paths, config, ids = _repo(tmp_path)
    drafts = {eid: _draft(eid) for eid in ids}
    write_jsonl(paths.runs / "dev" / "spare" / "predictions.jsonl", list(drafts.values()))
    monkeypatch.setenv("CODELOOP_UI_USER", AUTH["username"])
    monkeypatch.setenv("CODELOOP_UI_PASS", AUTH["password"])
    settings = ServeSettings(mode="review", data_dir=tmp_path / "vol", coder_id=CODER, batch="spare", version="dev")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_app(settings, paths.root), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    yield {"base": f"http://127.0.0.1:{port}", "ids": ids, "drafts": drafts, "events": settings.events_path}
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = None
        for kwargs in ({"channel": "chrome"}, {}):  # an installed Chrome, else `playwright install chromium`
            try:
                browser = p.chromium.launch(headless=True, **kwargs)
                break
            except PlaywrightError:
                continue
        if browser is None:
            pytest.skip("no browser Playwright can launch")
        pg = browser.new_context(http_credentials=AUTH).new_page()
        pg.set_default_timeout(5000)
        expect.set_options(timeout=5000)
        pg.dialogs = []
        pg.decline = False  # set to answer the next confirm() with Cancel

        def on_dialog(d):
            pg.dialogs.append(f"{d.type}: {d.message}")
            if d.type == "confirm" and pg.decline:
                pg.decline = False
                d.dismiss()
            else:
                d.accept()

        pg.on("dialog", on_dialog)
        yield pg
        browser.close()


def _card(page, text):
    return page.locator(".field", has_text=text).first


def _open(page, served, eid, mode):
    page.goto(f"{served['base']}/encounter/{eid}")
    expect(page.locator("#modebar")).to_contain_text(f"mode: {mode}")


def _grade_and_accept(page, text, grade):
    _card(page, text).get_by_role("button", name="✓" if grade == "supported" else "✗").click()
    expect(_card(page, text).locator(f".chip.{grade}")).to_have_count(1)
    _card(page, text).get_by_role("button", name="Accept").click()
    expect(page.locator(".field.accepted", has_text=text)).to_have_count(1)


def _approve(page, served, eid):
    expect(page.locator("#modebar")).to_contain_text("pending before approve: 0 fields, 0 passages, 0 queries")
    page.get_by_role("button", name="Approve encounter").click()
    page.wait_for_url(served["base"] + "/")
    expect(page.locator("tr", has_text=eid)).to_contain_text("approved")


def _stored(served, eid):
    store = EventStore(served["events"])
    try:
        events = store.for_encounter(eid)
    finally:
        store.close()
    return events, replay(eid, CODER, served["drafts"][eid], events)


def test_review_flow_saves_every_action(served, page):
    eid = served["ids"][2]
    _open(page, served, eid, "review")
    assert page.dialogs == []  # the open event was accepted
    _card(page, "M1711").click()
    expect(page.locator("#note mark")).to_have_count(1)  # quotes in the passage text do not break the handler
    # remove a field before grading its passage: the passage must stay gradable (guidelines §4), or approve is stuck
    page.select_option("#r-dx-M1711", "unsupported")
    _card(page, "M1711").get_by_role("button", name="Remove").click()
    expect(page.locator("h3", has_text=ORPHANS)).to_have_count(1)
    orphan = page.locator(".field.touched", has_text="as drafted")
    orphan.get_by_role("button", name="✓").click()
    expect(orphan.locator(".chip.supported")).to_have_count(1)
    _grade_and_accept(page, "E119", "unsupported")
    # the line pointed at the removed diagnosis: re-point it (an Accept would leave approval blocked on the pointer)
    _card(page, "73562").get_by_role("button", name="✓").click()
    expect(_card(page, "73562").locator(".chip.supported")).to_have_count(1)
    page.fill("#p-line-73562-0", "E11.9")
    page.select_option("#r-line-73562-0", "wrong_value")
    _card(page, "73562").get_by_role("button", name="Edit").click()
    # the removed diagnosis was the first-listed one: the status bar says so until another is chosen
    expect(page.locator("#modebar .bad")).to_have_text("no diagnosis is marked first-listed")
    page.check("#f-dx-E119")
    page.select_option("#r-dx-E119", "judgment")
    _card(page, "E119").get_by_role("button", name="Edit").click()
    expect(page.locator("#modebar .bad")).to_have_count(0)
    page.get_by_role("button", name="Warranted", exact=True).click()
    expect(_card(page, "synthetic question?").locator("b")).to_have_text("warranted")
    _approve(page, served, eid)
    assert page.dialogs == []
    events, rec = _stored(served, eid)
    assert [e.type for e in events] == [
        "open", "remove", "grade_evidence", "grade_evidence", "accept", "grade_evidence", "edit", "edit", "grade_query", "approve",
    ]
    assert [(d.code, d.first_listed) for d in rec.label.diagnoses] == [("E119", True)]
    assert [(ln.code, ln.pointers) for ln in rec.label.lines] == [("73562", ["E11.9"])]
    assert rec.evidence_grades == {"dx:M1711#0": "supported", "dx:E119#0": "unsupported", "line:73562:0#0": "supported"}
    assert rec.query_grades == {"query:0": "warranted"} and rec.touches == 3


def test_blind_flow_reveals_the_draft_and_keeps_both_labels(served, page):
    eid = served["ids"][0]
    _open(page, served, eid, "blind")
    expect(page.locator(".banner")).to_have_count(1)
    assert "M1711" not in page.content()  # no draft on the page before the blind label is in
    # an empty blind label is refused (it is final, and once went in seven seconds after opening the encounter)
    with page.expect_event("dialog", predicate=lambda d: d.type == "alert"):
        page.get_by_role("button", name="Submit blind label").click()
    assert "no diagnoses yet" in page.dialogs[-1] and "mode: blind" in page.locator("#modebar").inner_text()
    # so is submitting over a code that was typed but never added
    page.fill("#add-dx-code", "J06.9")
    page.check("#add-dx-first")
    with page.expect_event("dialog"):
        page.get_by_role("button", name="Submit blind label").click()
    assert "never added" in page.dialogs[-1]
    _card(page, "Add diagnosis").get_by_role("button", name="Add", exact=True).click()
    expect(page.locator(".field b", has_text="J069")).to_have_count(1)
    page.fill("#add-line-code", "73562")
    page.fill("#add-line-mods", "26")
    page.fill("#add-line-ptr", "J069")
    _card(page, "Add line").get_by_role("button", name="Add", exact=True).click()
    expect(page.locator(".field b", has_text="73562")).to_have_count(1)
    page.get_by_role("button", name="Submit blind label").click()
    expect(page.locator("#modebar")).to_contain_text("mode: review")
    # edit the code before grading its passage: the drafted passage must stay gradable under its drafted ref
    page.fill("#c-dx-M1711", "M17.12")
    page.select_option("#r-dx-M1711", "specificity")
    _card(page, "M1711").get_by_role("button", name="Edit").click()
    expect(page.locator(".field b", has_text="M1712")).to_have_count(1)
    orphan = page.locator(".field.touched", has_text="as drafted")
    orphan.get_by_role("button", name="✗").click()
    expect(orphan.locator(".chip.unsupported")).to_have_count(1)
    _grade_and_accept(page, "E119", "supported")
    _grade_and_accept(page, "73562", "supported")
    page.get_by_role("button", name="Unwarranted", exact=True).click()
    expect(_card(page, "synthetic question?").locator("b")).to_have_text("unwarranted")
    _approve(page, served, eid)
    assert [d.split(":")[0] for d in page.dialogs] == ["confirm", "alert", "alert", "confirm"]
    assert page.dialogs[-1].startswith("confirm: Submit the blind label with 1 diagnosis code(s) and 1 line(s)? This is final.")
    events, rec = _stored(served, eid)
    assert [(e.mode, e.type) for e in events][:4] == [("blind", "open"), ("blind", "add"), ("blind", "add"), ("blind", "blind_submit")]
    assert [d.code for d in rec.blind_label.diagnoses] == ["J069"] and rec.blind_label.diagnoses[0].first_listed
    assert [(ln.code, ln.modifiers, ln.pointers) for ln in rec.blind_label.lines] == [("73562", ["26"], ["J069"])]
    assert [d.code for d in rec.label.diagnoses] == ["M1712", "E119"] and rec.touches == 1
    assert rec.evidence_grades == {"dx:M1711#0": "unsupported", "dx:E119#0": "supported", "line:73562:0#0": "supported"}


def test_refusals_reach_the_coder(served, page):
    eid = served["ids"][3]
    _open(page, served, eid, "review")
    with page.expect_event("dialog"):
        _card(page, "E119").get_by_role("button", name="Remove").click()
    assert page.dialogs == ["alert: choose a reason"]
    with page.expect_event("dialog"):
        page.get_by_role("button", name="Approve encounter").click()
    assert len(page.dialogs) == 2 and page.dialogs[1] == (
        "alert: not ready to approve: 3 field(s) need Accept, Edit or Remove (M1711, E119, 73562); "
        "3 passage(s) not graded, on M1711, E119, 73562; 1 provider query(ies) not graded (no. 1)."
    )
    # accepting a card must not hide that its passages are still ungraded (a coder got stuck exactly there)
    _card(page, "73562").get_by_role("button", name="Accept").click()
    expect(page.locator(".field.accepted .chip.ungraded")).to_have_count(1)
    expect(page.locator(".field.accepted .chip.ungraded")).to_contain_text("(not graded)")
    expect(page.locator("#modebar")).to_contain_text("2 fields (M1711, E119), 3 passages (M1711, E119, 73562), 1 queries")
    # Edit saves what is in the boxes; pressed on unchanged values it is refused with an explanation, not stored
    page.select_option("#r-dx-E119", "guideline")
    with page.expect_event("dialog"):
        _card(page, "E119").get_by_role("button", name="Edit").click()
    assert page.dialogs[2].startswith("alert: Nothing changed, so nothing was saved.")
    page.fill("#c-dx-E119", "")
    page.select_option("#r-dx-E119", "wrong_value")
    with page.expect_event("dialog"):
        _card(page, "E119").get_by_role("button", name="Edit").click()
    assert page.dialogs[3].startswith("alert: The code box is empty.")
    page.fill("#add-dx-code", "I10")
    with page.expect_event("dialog"):
        page.get_by_role("button", name="Approve encounter").click()
    assert "never added" in page.dialogs[4]
    events, rec = _stored(served, eid)
    assert [e.type for e in events] == ["open", "accept"] and rec.touches == 0


def test_pointers_codes_and_modifiers_are_checked_before_anything_is_final(served, page):
    eid = served["ids"][5]
    _open(page, served, eid, "review")
    # replacing a diagnosis leaves the X-ray line pointing at the removed code: shown on the card, blocks approval
    page.select_option("#r-dx-M1711", "guideline")
    _card(page, "M1711").get_by_role("button", name="Remove").click()
    expect(_card(page, "73562").locator(".bad")).to_have_text("M1711 ⚠")
    expect(page.locator("#modebar .bad")).to_have_text(
        "line 73562 points at M1711, which is not a diagnosis on the package; no diagnosis is marked first-listed"
    )
    # a category typed where the release needs a longer code is refused, with the reason
    page.fill("#add-dx-code", "K59.0")
    page.select_option("#r-add-dx", "missed")
    with page.expect_event("dialog"):
        _card(page, "Add diagnosis").get_by_role("button", name="Add", exact=True).click()
    assert page.dialogs[-1] == "alert: K59.0 is not a billable FY2027 ICD-10-CM code: more specific codes exist under it. Enter the full code."
    page.fill("#add-dx-code", "K59.00")
    page.select_option("#r-add-dx", "missed")
    _card(page, "Add diagnosis").get_by_role("button", name="Add", exact=True).click()
    expect(page.locator(".field b", has_text="K5900")).to_have_count(1)
    # an unexpected modifier asks first; Cancel saves nothing
    page.fill("#p-line-73562-0", "K59.00")
    page.fill("#m-line-73562-0", "26,LF")
    page.select_option("#r-line-73562-0", "wrong_value")
    page.decline = True
    with page.expect_event("dialog"):
        _card(page, "73562").get_by_role("button", name="Edit").click()
    assert page.dialogs[-1].startswith("confirm: LF is not a modifier this project expects (") and "Save it anyway?" in page.dialogs[-1]
    events, rec = _stored(served, eid)
    assert [e.type for e in events] == ["open", "remove", "add"] and rec.label.lines[0].pointers == ["M1711"]
    # with the typing fixed the edit goes through and the pointer problem clears
    page.fill("#m-line-73562-0", "26,LT")
    _card(page, "73562").get_by_role("button", name="Edit").click()
    expect(_card(page, "73562").locator(".bad")).to_have_count(0)
    expect(page.locator("#modebar .bad")).to_have_text("no diagnosis is marked first-listed")  # M1711 was the first-listed one
    page.check("#f-dx-K5900")
    page.select_option("#r-dx-K5900", "judgment")
    _card(page, "K5900").get_by_role("button", name="Edit").click()
    expect(page.locator("#modebar .bad")).to_have_count(0)
    events, rec = _stored(served, eid)
    assert rec.label.lines[0].modifiers == ["26", "LT"] and rec.label.lines[0].pointers == ["K59.00"] and rec.touches == 4
    assert [(d.code, d.first_listed) for d in rec.label.diagnoses] == [("E119", False), ("K5900", True)]

