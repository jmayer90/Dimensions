# UX-01 — Continuous placement: keep dimensioning without re-invoking

**Milestone:** M2 Fluency
**Effort:** M
**Depends on:** — (test coverage from `FND-06` strongly recommended first)
**Version impact:** Patch. Additive and default-off, or default-on with an obvious exit.

## Problem

Every annotation requires a fresh trip to the sidebar. `CADDIM_OT_CreateDimension.modal()` returns `{"FINISHED"}` immediately after `_create_dimension()` succeeds — at two separate sites, one for the click path and one for the confirm path — and the same pattern appears in the angle, area, guide, and measure operators.

Dimensioning is inherently repetitive. Annotating a part means placing five, ten, thirty dimensions in a row. Each one currently costs: move the mouse to the N-panel, click **Create Dimension**, move back to the model, place. The overhead exceeds the actual work.

Every CAD tool and every comparable Blender add-on keeps the tool active until the user dismisses it. This is the single most-reported friction point in tools of this type, and it is the difference between something people evaluate and something people adopt.

## Why it matters for 1.0

Listed in the 1.0 gate under capability. It is also the highest ratio of perceived improvement to implementation cost in the entire backlog.

## Approach

**Restart instead of finishing.** After a successful commit, reset the operator to its initial stage and return `{"RUNNING_MODAL"}` rather than `{"FINISHED"}`. Preserve constraint choices that the user would expect to persist — axis lock and offset distance — and clear the per-annotation state: both snaps, numeric input, and preview.

Which state persists across a repeat is the main design decision, so decide it deliberately and document it:

- **Persist:** axis constraint, offset distance, dimension type, and any style choices made during the session.
- **Clear:** start and end snaps, typed numeric input, hover state, and the offset plane (it is derived per dimension).

**Exit clearly.** `Esc` and right-click already cancel. In continuous mode they must exit the tool entirely rather than only stepping back a stage — the user needs one reliable way out. Since `Esc` currently clears numeric input first, then steps back, the full sequence from a fresh stage should reach exit rather than looping.

**Show that it is active.** A user who does not realize the tool is still running will be confused by their next click creating a dimension. The status text drawn by `_draw_interaction_status()` must say so, and Blender's header status area should show the available actions.

**Make it a preference, not a mode.** Add a "Continuous placement" preference in `FND-04`'s Interaction section. Recommend defaulting it **on** — it matches every comparable tool — provided the exit is obvious and the status text is clear. If defaulting on, say so in the CHANGELOG, since it changes behavior for existing users.

**Apply consistently.** All five creation operators should behave the same way. `create_guide` and `measure` benefit at least as much as `create_dimension`, since guides in particular are placed in groups.

## Acceptance criteria

- [ ] After committing, the tool returns to its first stage and accepts another placement with no further invocation.
- [ ] Axis constraint, offset distance, and dimension type persist across repeats; snaps, numeric input, and preview are cleared.
- [ ] `Esc` from a fresh stage exits the tool; right-click exits from any stage.
- [ ] Viewport status text shows that the tool is active and how to exit.
- [ ] Each committed annotation is a separate undo step — undoing once removes one dimension, not the whole session.
- [ ] The behavior is a preference, and its default is documented in the CHANGELOG.
- [ ] Applied to `create_dimension`, `create_angle`, `create_area`, `create_guide`, and `measure`.
- [ ] Switching mode, changing the active object, or entering another modal operator ends the session cleanly with no leaked preview state.
- [ ] `DESIGN.md` interaction contract describes continuous placement and what persists.
- [ ] README describes the behavior in Getting started.

## Code map

- `dimensions/operators/create_dimension.py` — the two `{"FINISHED"}` returns after `_create_dimension()` succeeds, plus `_step_back()` and cancel handling.
- `dimensions/operators/create_angle.py`, `create_area.py`, `create_guide.py`, `measure.py` — same pattern.
- `dimensions/interaction.py` — shared reset logic belongs here rather than duplicated per operator.
- `dimensions/drawing.py` — `_draw_interaction_status()`.
- `dimensions/preferences.py` — the preference (`FND-04`).

## Verification

- State-machine tests (from `FND-06`) asserting that a commit in continuous mode returns to the start stage with the correct fields cleared and preserved.
- A test asserting each repeat is an independent undo step.
- A test asserting the session ends cleanly on mode change, leaving no preview state.
- A test that continuous mode off preserves exactly today's behavior.

## Out of scope

- Chain and baseline dimensions — `DIM-01`. Those are a *related* annotation series with shared geometry, not just repeated invocation. Continuous placement is a prerequisite, not a substitute.
- Repeating the last annotation's full style onto new ones beyond what persists above — `OUT-03`.
- A radial/pie menu or other invocation UI.

## Invariants

- **One interaction contract.** All five tools must repeat identically. A tool that behaves differently on repeat is worse than one that does not repeat.
- **Preview before commit.** Each repeat starts with a clean preview; no state from the previous annotation may leak into the next one's preview.
