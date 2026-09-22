# 05 — Grounding is not support

This is the most important limitation in the server, and the one most likely to be glossed over by anything built on top of it.

## The problem, in one example

`build_evidence_table` matches deterministically — no LLM inside the server. Ask it for evidence that metformin treats diabetes, and among the rows it returns is this one, live from Europe PMC:

```
[substring]  ...metformin, specifically in «anxiety», diabetes/seizure-induced cog...
```

Both terms are present. The snippet is real, the article is real, the provenance is verifiable. And it says nothing whatsoever about metformin treating diabetes.

Now imagine the sentence had been *"metformin did **not** improve diabetes outcomes"*. A substring matcher scores that identically to *"metformin improved diabetes outcomes"*. The terms co-occur in both. **Co-mention is not support, and a deterministic matcher cannot tell the difference.** If your tool calls that column `supporting_evidence`, you have built a machine for laundering coincidence into citations.

## What the server does about it

Three things, none of which "solve" it — the point is to stop the problem being invisible.

**1. Naming.** The field is `candidate_evidence`, not `supporting_evidence`. Absence is `no_candidates`, not `unsupported` — once matches are only candidates, their complement can't claim to be unsupported either.

**2. Every row declares how it matched**, ranked strongest first:

| `match_type` | What it means | How much to trust it |
|---|---|---|
| `relation` | A relation-typed annotation (`Gene Drug`, `Gene Disease`, or `Disease Drug Relationship`) that explicitly links two entities | Strongest available — **still not an assertion** |
| `entity` | Surface text matches, and at least one term also matched an ontology tag | Middling |
| `substring` | Both terms appear in one annotation span and nothing more is known | Weak |
| `abstract_cooccurrence` | Terms co-occur only in a title+abstract window (annotation pass found nothing) | Weakest — still co-mention, not support |

Surface text is authoritative: a wrong ontology tag (e.g. Ravulizumab tagged as tocilizumab) cannot invent a hit. Short all-caps abbreviations match case-sensitively — pass expansions as term-list alternatives.

That ranking does real work. On the live query above, the three ontology-grounded rows sort above the coincidence, which sinks to the bottom as `substring`.

**3. A caveat travels in the payload**, not just in the docs, so a model that never read this page still sees it.

## Why `relation` is still not enough

The obvious hope is that relation-typed annotations rescue you: surely an annotation that explicitly links a gene and a disease is an assertion? We checked against the live API. It isn't.

Relation annotations carry **no polarity field**. Here is a real one, tagged `HSP90B1` + `cancer`:

> *"Although we did observe proteins that **may be** directly relevant to cancer (prognosis, treatment or response), such as HSP90B1, **which is worth further investigation in future studies**…"*

That is a hedge — the authors are explicitly saying they don't know yet. The annotation records that the two entities are related in this sentence, not what the sentence claims about them. They're also not reliably sentence-level: that `exact` spans several sentences, and relation annotations carry no `prefix`/`postfix` at all, just the span.

## Why not just add an LLM

Because the server would then be making the judgement, invisibly, with no audit trail — and the client already has a model. Putting one inside the tool means:

- non-determinism in something the benchmark needs to be reproducible
- a second, hidden place where reasoning happens
- a confident-sounding `supported: true` with nothing behind it

The honest division of labour is: **the server returns evidence with its provenance and its weaknesses labelled; the client reasons about it.** That's also why there's a `caveat` string in the response and why tool descriptions say "read the snippet" rather than implying the matching already did.

## What this means if you build on it

- Don't present `candidate_evidence` to a user as "the evidence". Have your model read the snippets and decide.
- Treat `substring` rows with real suspicion; they are where the coincidences live.
- Check `retraction_status` and `access_tier` on every row before quoting it. Retracted sources are labelled, not removed, precisely so you can see them.
- `no_candidates` with `reason: "not_annotated"` means *we could not look*, not *we looked and found nothing*. Those are very different claims and the reason codes exist to keep them apart.
