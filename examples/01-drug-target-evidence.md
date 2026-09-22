# 01 — Drug–target evidence

**Retrieved 2026-09-18.** Claim under test: *"Metformin is used to treat type 2 diabetes."*

The chain is `search_literature` → `build_evidence_table`. The interesting part is the last
row. (Transcript captured 2026-09-18; under R32 surface text is required for every hit —
ontology tags only upgrade `match_type`.)

## Step 1 — find openly licensed papers

```python
await search_literature("metformin AND diabetes", open_access_only=True, limit=6, abstract="none")
```

```
MED:42636218     OPEN_ACCESS  cc by        Antidiabetic medications and risk of cogni…
MED:42630468     OPEN_ACCESS  cc by-nc     GABA as an Overlooked Mediator of Metformi…
MED:42653759     OPEN_ACCESS  cc by        Special Issue "Metformin: Mechanism and Ap…
MED:42719233     OPEN_ACCESS  cc by        Real-world outcomes of sitagliptin and sit…
MED:42639277     OPEN_ACCESS  cc by        Rate and Characteristics of Metformin Use…
MED:42652248     OPEN_ACCESS  cc by        Metformin Exposure in Pregnancy and Fetal…
```

Note `cc by-nc` on the second: all six are `OPEN_ACCESS`, and they do not all permit the same
reuse. That is why the licence string travels with the tier.

## Step 2 — build the table

```python
await build_evidence_table(
    "Metformin is used to treat type 2 diabetes",
    ids,
    terms={"subject": "metformin", "object": "diabetes"},
)
```

`terms` is required. The server runs no LLM, so it cannot parse the claim — `claim` is carried
through as a label only.

```
match types: {'entity': 3, 'substring': 1}

[entity   ] tags=['diabetes pregn ind']
     …Metformin Use in «Gestational Diabetes» Diabetes…
[entity   ] tags=['diabetes mellitus e08e13']
     …GDM or overt «diabetes» is diagnosed, metformin…
[entity   ] tags=['metformin']
     …diabetes is diagnosed, «metformin» should be evaluated…
[substring] tags=['anxiety dis']
     …metformin, specifically in «anxiety», diabetes/seizure-induced cog…

no_candidates: [('MED:42636218', 'no_match')]
```

## What to notice

**The last row is a coincidence, and the server says so.** Its `exact` is *anxiety*. It
matched only because "metformin" and "diabetes" happen to appear in the surrounding text. It
tells you nothing about the claim — and it sorts last, as `substring`, because no ontology tag
tied either search term to a recognised entity. The three `entity` rows above it did have that
grounding.

This is the whole argument of [docs/learn/05](../docs/learn/05-grounding-is-not-support.md):
the table is called `candidate_evidence`, not `supporting_evidence`, because a deterministic
matcher cannot tell *"metformin improved diabetes outcomes"* from *"metformin did **not**
improve diabetes outcomes"*.

**One article is accounted for explicitly.** `MED:42636218` appears in `no_candidates` with
`reason: "no_match"` — we looked and found nothing. That is a different claim from
`"not_annotated"` (we could not look at all) or `"upstream_error"` (the lookup failed), and
the reason codes exist to keep them apart. Every ID you pass appears in exactly one of the two
lists.

**The response carries its own caveat**, so a model that never read these docs still sees it:

> These are CANDIDATE rows: each shows that the terms co-occur in the snippet, not that the
> article supports the claim…

**Provenance covers both calls.** `provenance.sources` has two entries — the batched metadata
search and the annotations request — each with its own URL, SHA-256 and `hash_scope`.
