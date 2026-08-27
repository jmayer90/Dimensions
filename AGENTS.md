# Agent instructions

Follow [CONTRIBUTING.md](CONTRIBUTING.md). It covers project scope, build and test commands, code style, and the documentation expectations that apply to every change.

Two points bear repeating because they are the most common failure modes here:

- **Documentation is part of the change set.** When a request alters product behavior, a workflow, or the architecture, update the affected durable docs — `README.md`, files under `docs/`, the extension manifest, and this file — in the same change. Always add a `docs/CHANGELOG.md` entry for user-visible changes, and check the change against the design invariants and roadmap in `docs/DESIGN.md`.
- **Scope is enforced.** Dimensions never modifies mesh geometry. Do not add geometry-authoring features, however small the increment.
- **Schema changes require a path.** New persisted settings or registries must advance `CURRENT_SCHEMA_VERSION`, add an idempotent migration, and include a released-file fixture and lifecycle assertion before release.
- **Roadmap status is explicit.** When work starts, ships, becomes partial, or is blocked, update both its ticket `Status` header and the table in `docs/tickets/README.md`; do not leave delivery state implicit in prose or unchecked acceptance lists.
