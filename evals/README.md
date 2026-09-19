# Benchmark

Two layers, because they measure different things.

## Layer 1 — contract & regression suite (this directory, working today)

```bash
uv run python -m evals.run          # replay recorded cassettes: deterministic, offline, in CI
uv run python -m evals.run --record # refresh cassettes from the live API
uv run python -m evals.run --live   # call the live API and record anything new
uv run python -m evals.report       # per-category breakdown
uv run python -m evals.report --all # movement across runs
```

35 cases across retrieval, grounding and refusal. It runs entirely from `cassettes/`, so it
is deterministic and needs no network. A request that was never recorded raises `CassetteMiss`
rather than quietly becoming a live call — a cassette layer that falls through to the network
is not deterministic.

**This is a contract suite, not a retrieval score.** A fixed query replayed from a cassette
measures the query the case author wrote, not the tool's ability to choose one. Scored
retrieval belongs to the agent layer.

## The circularity problem, and how the gold sets avoid it

A gold set built with this server's own `search_literature` would grade the tool against its
own output. Every case therefore declares `gold_provenance`, and anything marked
`provisional_self_derived` is scored **separately and excluded from the headline number**.

Right now nothing is provisional — every case comes from an outside source:

| Category | Source | Licence | Why it's independent |
|---|---|---|---|
| retrieval (15) | [PubMedQA](https://github.com/pubmedqa/pubmedqa) PQA-L | MIT | Expert-written questions keyed to real PMIDs. Can we find the paper from the question alone? |
| grounding (12) | PubMedQA `CONTEXTS` | MIT | Sentences a third party copied out of each abstract. Text we return must actually contain them. |
| refusal (8) | [Retraction Watch](https://gitlab.com/crossref/retraction-watch-data) via Crossref | CC0 | Retraction truth from outside Europe PMC — which matters, because the server derives retraction status from Europe PMC's own `pubTypeList`. |

Regenerate the cases (downloads to `.cache/`, which is gitignored — we commit derived cases,
not the datasets):

```bash
uv run python -m evals.goldsets.build --retrieval 15 --grounding 12 --refusal 8
```

### One finding worth recording

Retraction Watch and Europe PMC disagree on `MED:14973990`. RW classes it a `Retraction` with
reason *"Retract and Replace; Withdrawn as Out of Date"*; Europe PMC records it as `"Update in"`
pointing at a 2016 Cochrane revision. It was **superseded editorially, not retracted for
misconduct** — the sources disagree on taxonomy, not fact. The builder therefore excludes
`Retract and Replace`, `Withdrawn as Out of Date` and `Upgrade/Update of Prior`, so the suite
tests agreement about retraction rather than about vocabulary.

That disagreement is the whole argument for independent gold sets: a self-derived one could
not have surfaced it.

## How hard is it actually?

Worth being honest. On the 15 retrieval cases the gold PMID is ranked **1st in 12 of 15**,
median rank 1 — against result sets of up to 5,906 hits. That is real retrieval, but PubMedQA
questions are derived from paper titles, so they are friendlier than a clinical question typed
by a person. Read 100% as "the contract holds", not "retrieval is solved".

## Layer 2 — agent layer (not built yet)

Where retrieval is actually *scored*: a pinned model chooses its own queries against the live
server, over N runs, reporting per-case pass rate (k/N). Variance at the tool layer is zero by
construction — deterministic tools replaying fixed cassettes — so the agent layer is the only
place run-to-run variance is real. It will run on demand, never in CI.
