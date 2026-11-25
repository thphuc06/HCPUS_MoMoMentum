# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. Layout: **single-context**.

This repo already has its own places for decisions and domain rules. Use them; don't create parallel files for the same purpose.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root. It doesn't exist yet; `/domain-modeling` creates it when the first term is settled. Write it in Vietnamese with technical terms kept in English, like the rest of the docs.
- **`docs/decisions/`**: the ADRs (this repo's equivalent of `docs/adr/`). Read the ones that touch the area you're about to work in. The list with statuses is in `docs/decisions/README.md`.
- **`docs/ba/02-business-rules.md`**: business constraints (BC-xx) and business rules (BR-xx). Treat them as domain rules, and cite them by id.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront.

## Writing an ADR

When a skill says "record an ADR" or "create `docs/adr/NNNN-...`", write it in `docs/decisions/` instead, following `docs/decisions/README.md`:

- File name `NNNN-tieu-de-ngan.md`, the next number after the highest existing one. Copy `docs/decisions/template.md`.
- Status is one of `Đề xuất`, `Đã chốt`, `Thay thế bởi ADR-NNNN`. Never delete an old ADR; mark it superseded.
- Add a row to the "Danh sách" table in `docs/decisions/README.md`.
- If the ADR settles a question in `docs/requirements/open-questions.md`, tick it there and link the ADR.
- Add an entry to `docs/ai-log/` (see `CLAUDE.md`).

## File structure

```
/
├── GLOSSARY.md              (created lazily)
├── docs/decisions/          ADRs: NNNN-*.md, template.md, README.md (index)
├── docs/ba/02-business-rules.md
└── agent/, gateway/, libs/, frontend/, ...
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0002 (xác nhận trước khi ghi), but worth reopening because…_
