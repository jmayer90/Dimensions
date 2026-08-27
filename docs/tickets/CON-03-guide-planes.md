# CON-03 — Guide planes and an active construction plane

**Milestone:** M3 Construction
**Status:** ⛔ Blocked — waiting on `CON-02`.
**Effort:** L
**Depends on:** CON-02
**Version impact:** Patch to add planes. Minor trigger 2 if the active plane changes how existing axis constraints resolve.

## Problem

Construction geometry is limited to lines and points. There is no plane.

Two distinct needs:

**Saved guide planes.** A plane through three points, or a point and a normal, or offset from a face. Useful in its own right — section planes, working planes, reference datums — and as a snap target where a point can be constrained to lie on it.

**An active construction plane.** The more consequential idea. Axis constraints today are world X/Y/Z, with local axes coming in `UX-03`. Neither helps when the work is on an arbitrary sloped surface. Every CAD tool solves this the same way: the user sets a working plane and all subsequent input happens in it.

Without a construction plane, dimensioning anything not aligned to the world axes means fighting the constraint system. With one, the same operations become natural, and `CON-02`'s offsets and `CON-04`'s spacing become far more powerful because they operate in a meaningful frame.

## Why it matters for 1.0

The largest capability gap for construction work on non-axis-aligned geometry. Not a 1.0 gate item, and reasonable to defer past 1.0 — but if the tool is to support dimensionally built construction, this is the ticket that most delivers it.

## Approach

Split into two PRs: saved planes first, active plane second. The first is straightforward and independently useful; the second touches the interaction contract and deserves separate review.

### Part 1 — Guide planes as objects

Follow the guide and guide-point pattern: an Empty in the `Construction Guides` collection with a property group storing the definition. Support definition by three points, by point plus normal, by an existing face, and by offset from another plane. Store the *definition*, resolving position like `CON-02`'s derived guides, so a plane defined on geometry follows it.

Represent visually as a bounded grid rather than an infinite plane — an infinite plane is unreadable in a viewport. Make the displayed extent a user property; it is presentation, not definition.

As a snap target, a plane constrains a point to lie on it rather than snapping to a discrete position. This is a genuinely new kind of snap candidate — a surface constraint rather than a point — so `snapping.py`'s candidate model needs to accommodate it. Verify that it does before starting, since it may require the candidate model change to come first.

### Part 2 — The active construction plane

One plane at a time is designated active. When one is active:

- Axis constraints resolve in plane space: two in-plane axes plus the normal.
- Free point placement without a snap lands on the plane rather than on a view-derived plane.
- Typed distances are measured in plane space.
- The viewport shows unambiguously which plane is active — this must be impossible to miss, or users will be confused by input landing somewhere unexpected.

Setting the active plane should be quick: pick a guide plane, pick a face, or use the world planes. A clear "no active plane" state must always be one action away.

**Interaction-contract impact.** Redefining what `X`, `Y`, and `Z` mean while a plane is active is a change to a documented contract. Decide deliberately: either the axis keys resolve in plane space when a plane is active, or plane-space axes get separate bindings. The first is more useful and matches CAD convention; the second is less surprising. Recommend the first with a loud active-plane indicator, and record the decision and the version trigger in `DESIGN.md`.

## Acceptance criteria

**Part 1**

- [ ] Guide planes are persistent objects in the scene-owned `Construction Guides` collection.
- [ ] Definable by three points, point plus normal, an existing face, or offset from another plane.
- [ ] Definitions resolve from sources and update when sources move, like `CON-02` guides.
- [ ] Displayed as a bounded grid with a user-controlled extent that is presentation only.
- [ ] A point can be constrained to lie on a plane during acquisition.
- [ ] Planes appear in the `UX-05` snap toggles and the `UX-02` manager.
- [ ] Lost sources produce a visible repair state.

**Part 2**

- [ ] One plane can be set active, and cleared, in a single action.
- [ ] The active plane is unmistakably indicated in the viewport.
- [ ] Axis constraints resolve in plane space per the documented decision.
- [ ] Unsnapped point placement lands on the active plane.
- [ ] Typed distances measure in plane space.
- [ ] `DESIGN.md` interaction contract documents the behavior, the decision, and its version trigger.
- [ ] README documents construction planes.

## Code map

- `dimensions/properties.py` — plane property group, active-plane scene property.
- `dimensions/collections.py` — creation, following the guide pattern.
- `dimensions/snapping.py` — surface-constraint candidates; check the candidate model supports this.
- `dimensions/interaction.py` — `constrained_delta()`, `axis_from_event()`, plane-space resolution.
- `dimensions/operators/create_guide.py` — plane creation operators.
- `dimensions/drawing.py` — grid rendering, active-plane indicator.
- `dimensions/scene_sync.py` — resolving derived planes.

## Verification

- Plane definition tests for each method, including degenerate cases: three collinear points, a zero-length normal.
- Tests that a point constrained to a plane lies on it within tolerance.
- Tests that axis constraints resolve correctly in plane space, including a plane at an arbitrary orientation.
- A test that clearing the active plane restores world-space behavior exactly.
- Derived-plane update and repair-state tests, as in `CON-02`.

## Out of scope

- Multiple simultaneously active planes.
- Projecting existing annotations onto a plane.
- Sectioning or clipping the view to a plane. Related and useful; separate ticket.
- Creating mesh geometry on a plane, which is excluded from this project.

## Invariants

- **One interaction contract.** If axis keys change meaning under an active plane, they must change identically in every tool.
- **Preview before commit.** With a plane active, the preview must show where the point lands *on the plane*, not where the cursor is.
- **Non-destructive annotation.** Planes are construction objects and never become geometry.
