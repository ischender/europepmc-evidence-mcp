# 03 — Retracted source (negative control)

**Retrieved 2026-09-18.** The case a literature agent must not get wrong: evidence that reads perfectly well and comes from a retracted paper.

## Setup

`MED:41220153` is retracted. Europe PMC records this properly — `pubTypeList.pubType` contains `"Retracted Publication"`, and `commentCorrectionList` carries a `"Retraction in"` pointer to the notice. It is also `OPEN_ACCESS` with full text available, so nothing about fetching it would raise a flag on its own.

```python
await build_evidence_table(
    "Insulin resistance can be attenuated by herbal extracts",
    ["MED:41220153", "MED:42652248"],
    terms={"subject": "insulin", "object": "resistance"},
)
```

## The result

```
[entity] MED:41220153  retraction=retracted  tier=OPEN_ACCESS
     …San Extract Attenuates «Insulin Resistance» Resistance in Obese…
[entity] MED:41220153  retraction=retracted  tier=OPEN_ACCESS
     …BACKGROUND Obesity-induced «insulin resistance» significantly contr…
[entity] MED:41220153  retraction=retracted  tier=OPEN_ACCESS
     …XHS in improving «insulin resistance» through metabolic…
```

These are good `entity`-grade matches — ontology-grounded, on-topic, from an open-access paper. Everything about them says "cite me". And the work has been retracted.

## Labelled, not dropped

The rows are returned, with `retraction_status: "retracted"` on each.

Silently filtering them out would be the intuitive choice and it is the wrong one: **a dropped row is indistinguishable from evidence that never existed.** The agent would see a thinner table and no reason for it, and would have no way to tell "this paper was excluded because it was retracted" from "this paper had nothing to say". Worse, it removes the agent's ability to report *why* a promising-looking line of evidence doesn't hold.

So the server labels and the client decides. The tool description says so explicitly, and the server `instructions` say retracted work must never be presented as ordinary evidence.

## The four states, and why `unknown` is not `none`

`retraction_status` is `none | withdrawn | retracted | unknown`.

`unknown` is load-bearing. Citation-network rows come from an endpoint that carries no publication-type fields at all, so for an unenriched row we genuinely cannot tell. A `null` or a `false` there would read as "not retracted" — a claim we have no basis for. `get_citation_network` defaults to `enrich=true` and spends one extra batched lookup to resolve it properly; when that lookup fails, the rows stay explicitly `unknown` and `enrichment_failed: true` says so.

## `withdrawn` is honestly weaker

Retraction is a real field. **Withdrawal is not** — Europe PMC publishes no withdrawal flag, and the only available signal is the word "Withdrawn" at the start of a preprint's title (5,551 such records). That is a heuristic, and it is labelled as one rather than dressed up as a field. Retraction is therefore the primary negative control in the benchmark; withdrawal is best-effort.
