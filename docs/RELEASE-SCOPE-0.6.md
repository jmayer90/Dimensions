# 0.6 release scope

The 0.6 release line keeps the tested, bounded workflows: persistent annotations,
measurements, construction guides, Grease Pencil generation, scale-correct SVG/PDF,
and the optional single-page border and fixed title block. The 0.6 hardening tickets
`FND-12`, `OUT-06`, and `FND-13` are included. The installed sidebar gives Output a
prominent position immediately after creation tools, with labeled snap controls one panel below.

## Outside 0.6

- **Topology-changing modifier correspondence for live Area or face guides.** Face
  identity must be unique and structurally unchanged before an evaluated Area value
  is authoritative. Other modifier outcomes use the existing visible fallback or
  repair state. Face guides use base-mesh identity. Automatic correspondence after
  topology changes needs a stable identity contract, not a guessed face match.
- **Arbitrary Chain or Baseline member reordering.** The unexposed helper was removed
  from the release line. Chain insertion, deletion, reattachment, and repair remain;
  they have defined effects on the shared joints. Baseline members can still be
  acquired and edited through those supported workflows.
- **General drawing-document templates.** The fixed single-page title block remains
  supported. Multi-sheet documents, arbitrary templates, and schedules require a
  separate layout model and usability study before they become release candidates.

`experimental/post-0.6-feature-candidates` preserves the reviewed candidate before
this scope cut, including the removed helper. It is a place to investigate those
future contracts, not an alternate 0.6 release artifact. No persisted properties
were removed and schema v15 is unchanged.

## Release gate

Blender 5.1.2 and 5.2.2 Linux validation, installed UI inspection, performance
measurements, and the passing Windows/Linux/macOS release-candidate CI matrix are
recorded in [QA-REVIEW-2026-09-28.md](QA-REVIEW-2026-09-28.md). A separate
foreground supported-platform review and deliberate schema-freeze decision remain
before a 1.0 compatibility promise.
