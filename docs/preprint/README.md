# Preprint — v0.2.0 draft

`preprint.md` is the draft of *Substrate-alignment primitives for verifiable multi-entity agent systems*, the optional preprint named in the original extraction plan as a v0.2.0 deliverable.

The draft follows arxiv-style academic structure: abstract, introduction, related work, primitive surface, conformance, reference implementation, production-deployment evidence, discussion, conclusion, references.

## Status

**Pre-v0.2.0 draft.** Not yet submitted. Authors and affiliations are placeholders.

The intent is to publish on arXiv concurrently with the v0.2.0 tagged release of the repository. Until then, the draft is a stable reference for the standard's framing and an entry point for reviewers who prefer narrative to specification text.

## Building

The draft is written in GitHub-flavoured Markdown for readability on the repository front page. For a LaTeX version (arxiv submission, journal review), convert with [Pandoc](https://pandoc.org/):

```bash
pandoc preprint.md \
    --from gfm \
    --to latex \
    --standalone \
    --bibliography references.bib \
    --citeproc \
    -o preprint.tex
```

A `references.bib` mirroring the inline references can be generated from the references section; until then the inline citations stand as the canonical record.

## Contributions

If you find a factual error, a missing citation, or a clarity issue, please open a repository issue tagged `preprint`. Substantial edits land via pull request.
