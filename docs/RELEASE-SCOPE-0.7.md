# 0.7 release scope

User testing of the 0.6.0 build found broken tools, tools that could not be explained,
and too many concepts for the value they added. 0.7 keeps a smaller set of tools and
makes each of them work predictably. The decisions and acceptance criteria are recorded
in [UX-10](tickets/UX-10-focused-toolset.md).

## Kept

- Linear dimensions, with Chain as a Create Dimension mode that places ordinary
  dimensions end to end.
- Angle and area dimensions, the transient Measure tool, and saved measurements.
- Guide lines, offset guides, guide points, and guide-plane grids — all ordinary
  movable objects. Grids are real meshes that both Dimensions and Blender can snap to.
- The Annotation Manager, named styles, guided repair, Grease Pencil output, and
  scale-correct SVG/PDF with the single-sheet border and title block.

## Removed

| Removed | Why | What happens to saved data |
| --- | --- | --- |
| Baseline and persistent Chain sets | A set object broke expected per-dimension behavior; Baseline was unclear. | Converted to linear dimensions. |
| Radial, Diameter, Arc | The selection-and-fit workflow was not discoverable. | Deleted on load; names printed. |
| Datum, Coordinate, Elevation | Too many concepts for the workflows they served. | Annotations deleted; datums become guide points. |
| Centerline, Angular, Spacing, live offsets | Did not work reliably and were hard to explain. | Become fixed guide lines. |
| Active construction plane and its Use Selected/Face/View, World, and Clear actions | Produced camera-locked grids and remapped X/Y/Z in surprising ways. | Cleared. |
| Plane Offset and Cursor + Normal definitions | Imprecise, and redundant with movable grids. | Planes become grids on their last frame. |

## Release gate

The release gate in [DESIGN.md](DESIGN.md#release-gate) applies, plus
`tests/foreground_workflows.py` in a foreground Blender on each supported version.
Schema v16 shipped in 0.7.0.
