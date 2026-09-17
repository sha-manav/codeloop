import json

from codeloop.findings.cluster import cluster_findings
from codeloop.findings.extract import extract_findings
from codeloop.llm import FakeProvider, LLMCache, LLMClient, PromptStore, load_models_config
from codeloop.reporting.export import ExportError, export_release, license_check
from codeloop.review_ui.labels import build_labels
from codeloop.util.jsonl import read_jsonl
from tests.test_harness import BATCH, _repo, _seed_labels_and_events


def test_cluster_proposal_and_release_export(tmp_path):
    paths, config = _repo(tmp_path)
    ids = json.loads(paths.dev_split.read_text())["sets"][BATCH][:8]
    store = _seed_labels_and_events(paths, ids)
    build_labels(paths, batch=BATCH, version="v0", store=store, actor="tests")
    findings = extract_findings(paths, config, batch=BATCH)
    fid = findings[0].id
    provider = FakeProvider(lambda s, u, schema, p: {"proposals": [{"kind": "keep", "finding_ids": [fid], "pattern": "laterality corrections", "rationale": "consistent"}]})
    client = LLMClient(load_models_config(paths.models_yaml), PromptStore(paths.root / "prompts"), provider=provider, cache=LLMCache(None))
    out = cluster_findings(paths, client, batch=BATCH, store=store)
    assert out.exists() and "laterality corrections" in out.read_text() and fid in provider.calls[0]["user"]
    path, n = export_release(paths, config)
    assert n == 8
    recs = read_jsonl(path)
    assert recs[0]["diagnoses"] and recs[0]["coders"] == 1 and "evidence_spans" in recs[0] and recs[0]["source_license"].startswith("CC BY")
    assert all("text" not in s for r in recs for spans in r["evidence_spans"].values() for s in spans)
    config.sources["aci_bench"].license = "CC BY-NC-ND 4.0"
    try:
        license_check(config)
        raise AssertionError("expected ExportError")
    except ExportError:
        pass
