# 02 — Licence refusal

**Retrieved 2026-09-18.** Shows the behaviour that most distinguishes this server: a licence refusal is a *successful response the agent works around*, not a failure it retries.

## The request

`MED:24073682` is readable in Europe PMC — `inEPMC: "Y"`, the text is right there — but it is not openly licensed (`isOpenAccess: "N"`). That combination is exactly the middle tier a boolean `is_open_access` would erase.

```python
await fetch_article("MED:24073682", include_full_text=True)
```

## The response

```json
{
  "status": "restricted",
  "access_tier": "FREE_TO_READ",
  "licence": null,
  "reason": "Full text is only returned for OPEN_ACCESS records whose licence permits it. This record is FREE_TO_READ.",
  "available": ["metadata", "abstract", "annotations"]
}
```

No exception. No protocol error. No partial text.

## Why this shape

Had this been an error, the agent's most likely next moves are to retry it and then abandon the article entirely. As a **success** carrying `available`, the obvious next move is to use what *is* permitted:

```python
await get_annotations(["MED:24073682"], types=["Diseases"])
# status: "ok"
#   «geriatric syndromes»
```

The agent still gets grounded evidence from the paper. It just doesn't get the full text it isn't licensed to have.

Over the wire, through a real `tools/call`:

```
tools/call fetch_article -> restricted | FREE_TO_READ
```

## What is deliberately not done

**Never partial text.** Returning the first N characters would be worse than refusing: once a truncated blob is in the context window it is indistinguishable from a complete one, and the model will quote it as though it had read the paper.

**Never a silent downgrade.** Asking for full text and receiving only metadata, with no explanation, teaches the agent nothing. The refusal names the tier, the licence and the alternatives.

## The near-miss this caught

A subtlety worth recording. The obvious way to compute `OPEN_ACCESS` is "`isOpenAccess == "Y"` and some `fullTextUrlList` entry has `availabilityCode == "OA"`". That is **wrong**: MED-sourced records use `OA`, but PMC-sourced records use `F` ("Free") for the same thing — both with `isOpenAccess: "Y"` and a `cc by` licence.

Keying on the literal string `"OA"` silently downgrades every PMC-sourced open-access article to `FREE_TO_READ` and refuses text the licence plainly permits. Caught only by running the classifier over recorded fixtures of real records. See [docs/learn/03](../docs/learn/03-why-licence-and-provenance.md).
