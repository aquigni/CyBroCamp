from __future__ import annotations

from cybrocamp_memory.fact_cache import extract_fact_candidates, write_fact_cache_jsonl, load_fact_cache_jsonl
from cybrocamp_memory.schema import AuthorityClass
from cybrocamp_memory.search_index import SearchTermRecord


def _record(*terms: str, source_id: str = "source", authority: AuthorityClass = AuthorityClass.CANONICAL_VAULT) -> SearchTermRecord:
    return SearchTermRecord(
        source_id=source_id,
        source_uri=f"obsidian://{source_id}.md",
        chunk_id=f"chunk-{source_id}",
        chunk_index=0,
        content_hash=f"sha256:chunk-{source_id}",
        source_content_hash=f"sha256:{source_id}",
        span_start=0,
        span_end=10,
        text_preview="",
        authority=authority,
        terms=list(terms),
    )


def test_fact_candidates_are_cooccurrence_only_and_do_not_promote_authority():
    record = _record("cybrocamp", "hippocampus", "approval", source_id="vault")

    facts = extract_fact_candidates([record])

    assert facts
    assert all(fact.predicate == "co_occurs_with" for fact in facts)
    assert all(fact.authority is AuthorityClass.DERIVED_SUMMARY for fact in facts)
    assert all(fact.evidence_authority is AuthorityClass.CANONICAL_VAULT for fact in facts)
    assert all(fact.claims_user_approval is False for fact in facts)


def test_fact_cache_excludes_secret_like_terms_and_raw_text(tmp_path):
    record = _record("cybrocamp", "sk-SECRETSECRET", "token", "hippocampus")
    facts = extract_fact_candidates([record])
    output = tmp_path / "facts.jsonl"

    write_fact_cache_jsonl(output, facts)
    raw = output.read_text(encoding="utf-8")
    loaded = load_fact_cache_jsonl(output)

    assert "SECRETSECRET" not in raw
    assert "token" not in raw
    assert "text" not in raw
    assert loaded == facts


def test_fact_candidates_are_stable_across_input_order():
    left = _record("alpha", "beta", source_id="b")
    right = _record("alpha", "gamma", source_id="a")

    first = extract_fact_candidates([left, right])
    second = extract_fact_candidates([right, left])

    assert first == second
