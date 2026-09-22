# 03 — Why licence and provenance

Two design choices do most of the work in this server. Both are about making the agent's
epistemic position legible: what it may use, and where it got it.

## The three tiers

Access is an enum, never a boolean:

| Tier | Means | Full text? |
|---|---|---|
| `ABSTRACT_ONLY` | No full text anywhere in Europe PMC | No |
| `FREE_TO_READ` | Full text exists and you may read it, but it is not openly licensed | **No** |
| `OPEN_ACCESS` | Openly licensed (CC or similar) | Yes |

The middle tier is the whole point. "I can read it" and "I may redistribute it into a model's
context and quote it back to a user" are different permissions, and a boolean
`is_open_access` collapses exactly the distinction that matters. A real example from the
fixtures: `MED:24073682` has `inEPMC: "Y"` — the text is right there — and `isOpenAccess: "N"`.
It is `FREE_TO_READ`, and this server will not serve its full text.

### How the tier is actually computed

This took two corrections against live data, both worth knowing:

```python
if isOpenAccess == "Y" and full_text_is_reachable(record):
    OPEN_ACCESS
elif inEPMC == "Y" or inPMC == "Y":
    FREE_TO_READ
else:
    ABSTRACT_ONLY
```

**Correction 1: the flag alone isn't enough.** A record can claim openness with no actual
route to the text, so reachability is checked too.

**Correction 2 — the one that would have been a real bug.** The obvious reachability test is
"does `fullTextUrlList` contain an entry with `availabilityCode: "OA"`?" That is wrong.
MED-sourced records use `OA`; **PMC-sourced records use `F`** ("Free") for the same thing —
both with `isOpenAccess: "Y"` and a `cc by` licence. Keying on the literal string `"OA"`
silently downgrades every PMC-sourced open-access article to `FREE_TO_READ` and refuses text
the licence plainly permits. Caught only by running the classifier over a recorded fixture of
real records.

### The licence string travels too

The tier is not sufficient for a reuse decision. `cc by`, `cc by-nc`, `cc by-nd` and
`cc by-nc-nd` are *all* `OPEN_ACCESS` and permit very different things — `nd` forbids
derivatives, which is arguably what summarising is. So the raw string rides along with the
tier, into every record and every evidence row, and the agent (or the human) can make that
call with the facts in front of them.

## Refusal is a success

The most important line in the licence gate is that a refusal is **not an error**:

```json
{
  "status": "restricted",
  "data": {
    "access_tier": "FREE_TO_READ",
    "reason": "Full text is only returned for OPEN_ACCESS records whose licence permits it. ...",
    "available": ["metadata", "abstract", "annotations"],
    "record": { "id": "MED:…", "abstract": "…full abstract…", "title": "…" }
  }
}
```

If this were an exception or a protocol error, the agent's most likely next move is to retry
it, then give up on the article entirely. As a successful response carrying `record` (with the
**full** abstract, not a triage truncation) and `available`, the
obvious next move is to fall back to the abstract or the annotations — which is exactly what
you want. **Never** return partial full text as a compromise; a truncated blob is
indistinguishable from a complete one once it's in the context window.

There's a third status for the same reason: `outline`. When full text is too large, you get a
map of section names and sizes rather than a truncated dump, and re-request what you need.
Absence of content is always explicit.

### When metadata lies

Occasionally a record is flagged open access and `fullTextXML` returns 404 anyway. That 404 is
a *licence and availability signal*, not a transport failure — so it is deliberately excluded
from the retry list, and degrades into a `restricted` response explaining that metadata and
upstream availability disagree. Retrying it would turn a meaningful answer into a timeout.

## Provenance, and what a hash is actually worth

Every successful response carries:

```json
"provenance": {
  "provider": "Europe PMC",
  "sources": [
    {"resolved_url": "...", "content_sha256": "...", "hash_scope": "VOLATILE", "retrieved_at": "..."},
    {"resolved_url": "...", "content_sha256": "...", "hash_scope": "STABLE",   "retrieved_at": "..."}
  ],
  "query_params": {...},
  "server_version": "0.1.0"
}
```

**`sources` is a list, always** — even for one call. `fetch_article` with full text makes two
upstream calls; the evidence table makes up to ten. An envelope that hashed only the first
would silently drop the provenance for everything else, which would hollow out the one claim
this whole project is built on.

**The hash is taken before parsing.** `hash_content(response.content)`, not of our own
reshaped output. The point is that a third party can fetch the same URL and compare.

### The honest part: what the hash does *not* buy you

It is tempting to say "content hashing makes results reproducible". For search responses,
that's close to meaningless. Search bodies mutate constantly — `hitCount` changes as the
corpus grows, `citedByCount` changes as papers get cited. Re-fetch the same URL tomorrow and
the hash differs, without anything having gone wrong.

So each source declares a `hash_scope`:

- **`STABLE`** — published full text. Doesn't change. The hash is a genuine reproducibility
  claim, and someone can verify your quote came from that document.
- **`VOLATILE`** — search results. The hash identifies *this exact response*, which is useful
  for verifying a recorded fixture or detecting that a replayed cassette has drifted, and is
  not a claim anyone can recompute later.

Saying which is which is the difference between provenance and provenance theatre.

### Per-snippet hashes

Evidence rows also carry a hash of the individual snippet, over a defined canonicalisation:
`sha256(annotation_id + "\0" + prefix + exact + postfix)`, NFC-normalised, whitespace
collapsed.

The annotation `id` is in there deliberately. Europe PMC **re-mines** annotations, so snippet
text alone is not durable. Including the id means the hash *detects* a re-mine rather than
papering over it — if the same claimed evidence now hashes differently, you want to know.
