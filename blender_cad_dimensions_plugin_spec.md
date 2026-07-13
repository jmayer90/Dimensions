# Blender CAD Dimensions Add-on — Implementation Specification

## Purpose

Build a Blender add-on that provides persistent, CAD-like dimensions linked to mesh vertices, including vertices on different objects.

The add-on is intended to solve the limitations of Blender's built-in ruler and the MeasureIt add-on by making dimensions:

- Persistent.
- Selectable.
- Hideable.
- Renameable.
- Deletable.
- Editable.
- Linked to actual mesh vertices.
- Able to span multiple objects.
- Automatically updated when referenced objects or vertices move.
- Displayed as clean CAD-style annotations in the 3D Viewport.

The primary use case is woodworking, architectural modeling, and dimension-driven object layout in Blender.

---

# Core User Experience

## Create a dimension

1. User activates **Create CAD Dimension**.
2. User hovers over a mesh in Object Mode.
3. The nearest eligible vertex highlights.
4. User clicks the first vertex.
5. User hovers over the same object or another object.
6. User clicks the second vertex.
7. User moves the mouse to position the dimension-line offset.
8. User clicks to finish.

The new dimension appears in a dedicated collection:

```text
CAD Dimensions
└── DIM Board Width
```

## Manage a dimension

The user can:

- Select it in the Outliner.
- Select it in a sidebar list.
- Eventually click the drawn dimension line directly.
- Rename it.
- Hide or show it.
- Delete it.
- Change its dimension type.
- Change its offset.
- Change display precision.
- Reattach either endpoint to another vertex.
- Inspect whether either anchor is linked, recovered, or detached.

## Supported dimension types

Initial version:

- Aligned distance.

Possible future versions:

- Global X distance.
- Global Y distance.
- Global Z distance.
- Local-axis projected distance.
- Angular dimension.
- Radius and diameter dimension.
- Face-to-face dimension.
- Edge length dimension.
- Center-to-center dimension.

---

# Recommended Architecture

Use a hybrid architecture:

- One Blender Empty object per dimension.
- Custom properties stored on the Empty.
- The Empty acts as the persistent scene entity.
- GPU draw handlers render the visible CAD-style annotation.
- Font drawing renders the dimension label.
- The Empty appears in the Outliner.
- The Empty can be selected, hidden, renamed, and deleted normally.
- A dedicated sidebar exposes dimension properties.
- A custom viewport hit test can later make the drawn line clickable.

Do not represent every dimension line and arrow as normal mesh or curve objects in the first version.

Do not store all dimensions only in one scene-level collection without corresponding Blender objects.

The Empty is the persistent owner of the dimension data. The viewport graphics are only a visual representation of that data.

---

# Blender Concepts Required

## `bpy`

Blender's main Python API.

## Operator

A command or action, such as:

- Create Dimension.
- Reattach Start.
- Reattach End.
- Delete Dimension.

## Modal operator

An operator that stays active and receives mouse and keyboard events until it finishes or is canceled.

Needed for:

- Hovering vertices.
- Picking dimension endpoints.
- Setting dimension offset.
- Reattaching endpoints.
- Viewport dimension selection.

## Panel

A user interface shown in the 3D Viewport sidebar.

## Property

Persistent data saved in the `.blend` file.

## PropertyGroup

A structured group of custom properties.

## Draw handler

A function Blender calls to draw custom geometry or text in the viewport.

Use:

- `POST_VIEW` for world-space graphics if needed.
- `POST_PIXEL` for screen-space lines, arrows, text, selection, and hit testing.

## Context

The current Blender state, including:

- Active area.
- Active region.
- Active object.
- Current mode.
- Current scene.
- Current view layer.

## Object coordinates vs world coordinates

A mesh vertex coordinate is local to its object:

```python
vertex_local = obj.data.vertices[index].co
```

Convert it to world space with:

```python
vertex_world = obj.matrix_world @ vertex_local
```

This conversion is fundamental to the entire add-on.

---

# Data Model

## Dimension object

Each persistent dimension is represented by one Empty object.

Recommended collection:

```text
CAD Dimensions
```

Recommended naming:

```text
DIM Width
DIM Board Length
DIM Inside Opening
```

The Empty should:

- Use `object_data=None`.
- Be hidden from rendering.
- Have a very small or unobtrusive viewport display.
- Store a custom `cad_dimension` property group.

---

# Anchor Model

Each endpoint needs:

- Target object pointer.
- Vertex index.
- Fallback local coordinate.
- Anchor status.
- Optional persistent vertex ID in a later version.

Recommended initial anchor structure:

```python
class CADDIM_PG_Anchor(bpy.types.PropertyGroup):
    target_object: bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
    )

    vertex_index: bpy.props.IntProperty(
        name="Vertex Index",
        default=-1,
    )

    fallback_local_co: bpy.props.FloatVectorProperty(
        name="Fallback Local Coordinate",
        size=3,
        subtype="XYZ",
    )
```

Future expansion:

```text
anchor_type
persistent_vertex_id
recovery_tolerance
status
```

Possible `anchor_type` values:

```text
VERTEX
OBJECT_LOCAL_POINT
WORLD_POINT
EDGE
FACE
```

The first version should implement only:

```text
VERTEX
OBJECT_LOCAL_POINT
```

---

# Dimension Property Model

Recommended initial structure:

```python
class CADDIM_PG_Dimension(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(default=False)

    start: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    end: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    dimension_type: bpy.props.EnumProperty(
        name="Dimension Type",
        items=[
            ("ALIGNED", "Aligned", "True point-to-point distance"),
        ],
        default="ALIGNED",
    )

    offset_pixels: bpy.props.FloatProperty(
        name="Offset",
        default=35.0,
        min=-1000.0,
        max=1000.0,
    )

    precision: bpy.props.IntProperty(
        name="Precision",
        default=3,
        min=0,
        max=8,
    )

    visible: bpy.props.BoolProperty(
        name="Visible",
        default=True,
    )

    locked: bpy.props.BoolProperty(
        name="Locked",
        default=False,
    )

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        default=(0.9, 0.65, 0.1, 1.0),
        min=0.0,
        max=1.0,
    )

    selected_color: bpy.props.FloatVectorProperty(
        name="Selected Color",
        subtype="COLOR",
        size=4,
        default=(1.0, 0.9, 0.2, 1.0),
        min=0.0,
        max=1.0,
    )
```

Attach to Blender objects:

```python
bpy.types.Object.cad_dimension = bpy.props.PointerProperty(
    type=CADDIM_PG_Dimension
)
```

---

# Object Creation

Recommended helper:

```python
DIMENSION_COLLECTION_NAME = "CAD Dimensions"


def get_or_create_dimension_collection(context):
    collection = bpy.data.collections.get(DIMENSION_COLLECTION_NAME)

    if collection is None:
        collection = bpy.data.collections.new(DIMENSION_COLLECTION_NAME)
        context.scene.collection.children.link(collection)

    return collection


def create_dimension_object(context, name="DIM Dimension"):
    collection = get_or_create_dimension_collection(context)

    dim_obj = bpy.data.objects.new(name, object_data=None)
    dim_obj.empty_display_type = "PLAIN_AXES"
    dim_obj.empty_display_size = 0.01
    dim_obj.hide_render = True

    collection.objects.link(dim_obj)

    dim_obj.cad_dimension.enabled = True

    return dim_obj
```

---

# Anchor Assignment

Store the selected object's vertex and fallback local coordinate.

```python
def set_anchor(anchor, obj, vertex_index):
    vertex = obj.data.vertices[vertex_index]

    anchor.target_object = obj
    anchor.vertex_index = vertex_index
    anchor.fallback_local_co = vertex.co
```

---

# Anchor Resolution

Resolve each anchor every time the viewport is redrawn.

```python
from mathutils import Vector


def resolve_anchor(anchor):
    obj = anchor.target_object

    if obj is None or obj.type != "MESH":
        return None, "MISSING_OBJECT"

    mesh = obj.data
    index = anchor.vertex_index

    if 0 <= index < len(mesh.vertices):
        local_co = mesh.vertices[index].co
        world_co = obj.matrix_world @ local_co
        return world_co, "LINKED"

    fallback = Vector(anchor.fallback_local_co)
    world_co = obj.matrix_world @ fallback
    return world_co, "DETACHED"
```

Possible statuses:

```text
LINKED
RECOVERED
DETACHED
MISSING_OBJECT
```

Initial version only needs:

```text
LINKED
DETACHED
MISSING_OBJECT
```

---

# Dynamic Updating

No explicit update handler is required for ordinary object transforms.

The draw function should resolve both anchors on every viewport redraw:

```python
start_world, start_status = resolve_anchor(props.start)
end_world, end_status = resolve_anchor(props.end)
```

This automatically tracks:

- Object translation.
- Object rotation.
- Object scaling.
- Parent transforms.
- Vertex movement when the same base-mesh vertex remains valid.

---

# Vertex Snapping in Object Mode

The add-on must implement its own vertex-picking logic.

Blender's native snapping system is not exposed as one simple reusable Python function.

## Picking sequence

On every mouse movement:

1. Convert mouse coordinates into a world-space ray.
2. Ray-cast against the evaluated scene.
3. Identify the hit object and hit face.
4. Examine the vertices of the hit face.
5. Convert those vertices to world coordinates.
6. Project those world coordinates back to screen space.
7. Choose the nearest vertex within a pixel threshold.
8. Draw a visual snap marker.

## Mouse ray

```python
from bpy_extras import view3d_utils
from mathutils import Vector


def get_mouse_ray(context, mouse_region_x, mouse_region_y):
    mouse = Vector((mouse_region_x, mouse_region_y))

    origin = view3d_utils.region_2d_to_origin_3d(
        context.region,
        context.region_data,
        mouse,
    )

    direction = view3d_utils.region_2d_to_vector_3d(
        context.region,
        context.region_data,
        mouse,
    )

    return origin, direction.normalized()
```

## Scene ray cast

```python
def raycast_from_mouse(context, mouse_x, mouse_y):
    origin, direction = get_mouse_ray(
        context,
        mouse_x,
        mouse_y,
    )

    depsgraph = context.evaluated_depsgraph_get()

    hit, location, normal, face_index, obj, matrix = (
        context.scene.ray_cast(
            depsgraph,
            origin,
            direction,
        )
    )

    if not hit or obj is None or obj.type != "MESH":
        return None

    return {
        "object": obj,
        "location": location,
        "normal": normal,
        "face_index": face_index,
    }
```

## Closest vertex on hit face

```python
def find_nearest_face_vertex(
    context,
    mouse_x,
    mouse_y,
    pixel_threshold=14.0,
):
    hit = raycast_from_mouse(
        context,
        mouse_x,
        mouse_y,
    )

    if hit is None:
        return None

    obj = hit["object"]
    face_index = hit["face_index"]

    if face_index < 0 or face_index >= len(obj.data.polygons):
        return None

    polygon = obj.data.polygons[face_index]
    mouse = Vector((mouse_x, mouse_y))

    best = None
    best_distance = pixel_threshold

    for vertex_index in polygon.vertices:
        vertex = obj.data.vertices[vertex_index]
        world_co = obj.matrix_world @ vertex.co

        screen_co = view3d_utils.location_3d_to_region_2d(
            context.region,
            context.region_data,
            world_co,
        )

        if screen_co is None:
            continue

        distance = (screen_co - mouse).length

        if distance < best_distance:
            best_distance = distance
            best = {
                "object": obj,
                "vertex_index": vertex_index,
                "world_co": world_co,
                "screen_co": screen_co,
            }

    return best
```

## Initial snapping policy

The first version should snap only to:

- Original mesh vertices.
- Visible vertices belonging to the ray-cast face.

Do not scan every vertex in the entire scene on each mouse move.

Possible future improvements:

- BVH cache.
- KD-tree cache.
- Edge midpoint snapping.
- Face center snapping.
- Screen-space candidate cache.
- Occlusion-aware snapping.
- Persistent snap preferences.
- Modifier-generated geometry mapping.

---

# Modal Create Dimension Operator

Use a modal state machine:

```text
PICK_START
PICK_END
SET_OFFSET
FINISHED
```

Recommended behavior:

## `PICK_START`

- Hover candidate vertex.
- Highlight candidate.
- Left click stores first anchor.
- Esc or right click cancels.

## `PICK_END`

- Hover candidate vertex on any object.
- Draw temporary line from first anchor to hover point.
- Left click stores second anchor.
- Esc or right click cancels.

## `SET_OFFSET`

- Project both anchors to screen space.
- Move dimension line perpendicular to the measured segment.
- Mouse motion adjusts pixel offset.
- Left click confirms.
- Enter confirms.
- Esc cancels creation.

Skeleton:

```python
class CADDIM_OT_CreateDimension(bpy.types.Operator):
    bl_idname = "caddim.create_dimension"
    bl_label = "Create CAD Dimension"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area.type != "VIEW_3D":
            return {"CANCELLED"}

        self.state = "PICK_START"
        self.start_snap = None
        self.end_snap = None
        self.hover_snap = None
        self.offset_pixels = 35.0

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "MOUSEMOVE":
            if self.state in {"PICK_START", "PICK_END"}:
                self.hover_snap = find_nearest_face_vertex(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                )

            elif self.state == "SET_OFFSET":
                self.update_offset(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                )

            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.state == "PICK_START":
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                self.start_snap = self.hover_snap.copy()
                self.state = "PICK_END"
                return {"RUNNING_MODAL"}

            if self.state == "PICK_END":
                if self.hover_snap is None:
                    return {"RUNNING_MODAL"}

                self.end_snap = self.hover_snap.copy()
                self.state = "SET_OFFSET"
                return {"RUNNING_MODAL"}

            if self.state == "SET_OFFSET":
                self.create_dimension(context)
                context.area.tag_redraw()
                return {"FINISHED"}

        if event.type in {"ESC", "RIGHTMOUSE"}:
            context.area.tag_redraw()
            return {"CANCELLED"}

        return {"PASS_THROUGH"}

    def create_dimension(self, context):
        dim_obj = create_dimension_object(
            context,
            "DIM Dimension",
        )

        set_anchor(
            dim_obj.cad_dimension.start,
            self.start_snap["object"],
            self.start_snap["vertex_index"],
        )

        set_anchor(
            dim_obj.cad_dimension.end,
            self.end_snap["object"],
            self.end_snap["vertex_index"],
        )

        dim_obj.cad_dimension.offset_pixels = self.offset_pixels

        for obj in context.selected_objects:
            obj.select_set(False)

        dim_obj.select_set(True)
        context.view_layer.objects.active = dim_obj
```

---

# Dimension Rendering

Use viewport draw handlers.

Recommended final architecture:

- `POST_PIXEL` for CAD-style dimension graphics.
- `blf` for text.
- `gpu` and `gpu_extras.batch` for lines and arrowheads.

## Why screen-space rendering

Screen-space rendering provides:

- Constant text size.
- Constant arrow size.
- Constant line width.
- Reliable click hit testing.
- Readability regardless of zoom.

## Screen-space dimension geometry

For each dimension:

1. Resolve both world-space anchors.
2. Project both to screen coordinates.
3. Compute the screen-space direction.
4. Compute a perpendicular vector.
5. Offset the dimension line.
6. Draw extension lines.
7. Draw dimension line.
8. Draw arrowheads.
9. Draw text.

```python
def get_screen_dimension_geometry(context, dim_obj):
    props = dim_obj.cad_dimension

    start_world, start_status = resolve_anchor(props.start)
    end_world, end_status = resolve_anchor(props.end)

    if start_world is None or end_world is None:
        return None

    start_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        start_world,
    )

    end_screen = view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        end_world,
    )

    if start_screen is None or end_screen is None:
        return None

    direction = end_screen - start_screen

    if direction.length < 0.001:
        return None

    direction.normalize()
    perpendicular = Vector((-direction.y, direction.x))

    offset = perpendicular * props.offset_pixels

    line_start = start_screen + offset
    line_end = end_screen + offset

    return {
        "anchor_start": start_screen,
        "anchor_end": end_screen,
        "line_start": line_start,
        "line_end": line_end,
        "start_world": start_world,
        "end_world": end_world,
        "start_status": start_status,
        "end_status": end_status,
    }
```

## Distance calculation

```python
def calculate_dimension_value(props, start_world, end_world):
    delta = end_world - start_world

    if props.dimension_type == "X":
        return abs(delta.x)

    if props.dimension_type == "Y":
        return abs(delta.y)

    if props.dimension_type == "Z":
        return abs(delta.z)

    return delta.length
```

## Basic unit formatting

```python
def format_dimension(context, value, precision):
    return bpy.utils.units.to_string(
        context.scene.unit_settings.system,
        "LENGTH",
        value,
        precision=precision,
    )
```

For woodworking, add a custom fractional-inch formatter later.

---

# CAD-Style Graphics

The dimension should eventually include:

- Start extension line.
- End extension line.
- Main dimension line.
- Inward or outward arrowheads.
- Centered label.
- Optional text background.
- Selected-state highlight.
- Detached-anchor warning color.
- Hover highlight.

Suggested visual states:

```text
Normal: configured color
Selected: brighter selected color
Hovered: temporary highlight
Detached: warning color
Hidden: not drawn
Locked: visually distinct icon in UI
```

---

# Clickable Dimensions

The visible line is GPU drawing, not normal Blender geometry.

Blender will not select it automatically.

Implement custom screen-space hit testing.

## Point-to-segment distance

```python
def point_to_segment_distance(point, start, end):
    segment = end - start

    if segment.length_squared == 0:
        return (point - start).length

    factor = (point - start).dot(segment) / segment.length_squared
    factor = max(0.0, min(1.0, factor))

    closest = start + segment * factor
    return (point - closest).length
```

## Selection logic

1. Project all visible dimensions.
2. Measure mouse distance to each dimension line.
3. Also test label rectangle and endpoint handles.
4. Pick the closest match under a pixel threshold.
5. Make the corresponding Empty active and selected.

Suggested threshold:

```text
6 to 10 pixels
```

Recommended initial design:

- Select dimensions through Outliner and sidebar first.
- Add viewport line selection after core creation and drawing work reliably.

Possible final interaction:

```text
Dedicated Dimension Select tool
```

or:

```text
Alt + Left Click
```

Avoid intercepting all normal left-click selection globally.

---

# Visibility, Rename, and Delete

Because each dimension is a real Blender object:

- Outliner rename works.
- Outliner hide works.
- `H` can hide the Empty.
- `X` can delete the Empty.
- Collection visibility can hide all dimensions.
- The add-on panel can expose explicit hide and delete buttons.

The draw handler must skip dimensions that are not visible:

```python
if dim_obj.hide_get():
    continue

if not dim_obj.visible_get(view_layer=context.view_layer):
    continue

if not dim_obj.cad_dimension.visible:
    continue
```

---

# Editing

Initial editing should use explicit sidebar buttons.

Do not begin with draggable gizmos.

## Reattach Start

1. User selects a dimension.
2. User clicks **Reattach Start**.
3. Modal vertex picker starts.
4. User selects a new vertex.
5. Only the start anchor is replaced.

## Reattach End

Same behavior for the end anchor.

## Editable properties

The sidebar should expose:

```text
Name
Dimension Type
Offset
Precision
Visible
Locked
Color
Start Object
Start Vertex Index
End Object
End Vertex Index
Start Status
End Status
Reattach Start
Reattach End
Delete
```

Possible later features:

- Drag endpoint handles.
- Drag offset handle.
- Double-click label to edit.
- Gizmo-based endpoint reattachment.
- In-viewport dimension type control.

---

# Sidebar Design

Recommended 3D Viewport sidebar tab:

```text
CAD Dim
```

Recommended layout:

```text
CAD Dimensions
────────────────────────
[Create Dimension]

Selected Dimension
────────────────────────
Name: Inside Width
Type: Aligned
Value: 11 7/16"
Offset: 35 px
Precision: 1/16"

Start
Board_Left
Vertex 5
Status: Linked
[Reattach Start]

End
Board_Right
Vertex 2
Status: Linked
[Reattach End]

[Hide]
[Delete]
```

Recommended dimension list:

```text
☑ DIM Board Length
☑ DIM Inside Width
☐ DIM Hidden Test
```

Possible controls:

```text
Show All
Hide All
Delete Selected
Delete All
```

---

# Fractional-Inch Formatting

The add-on is intended for woodworking, so custom fractional-inch formatting is important.

Recommended denominator options:

```text
2
4
8
16
32
64
```

Formatting examples:

```text
8.0 inches       -> 8"
11.4375 inches   -> 11 7/16"
38.125 inches    -> 3' 2 1/8"
7.999999 inches  -> 8"
```

Required rollover rule:

```python
if numerator == denominator:
    whole_inches += 1
    numerator = 0
```

The formatter must:

1. Convert Blender length to inches.
2. Split into feet and inches if enabled.
3. Separate whole and fractional inches.
4. Round to selected denominator.
5. Reduce the fraction using greatest common divisor.
6. Roll full fractions into the next whole inch.
7. Roll 12 inches into the next foot.
8. Avoid outputs such as `7 1/1"`.

The formatter should be independently tested.

---

# Vertex Identity Limitations

A vertex index is not permanently stable through all modeling operations.

It is generally stable when:

- Moving the object.
- Rotating the object.
- Scaling the object.
- Moving the referenced vertex.
- Moving unrelated vertices.
- Editing the mesh without rebuilding topology before the referenced index.

It may become invalid or point to another vertex after:

- Deleting vertices.
- Dissolving geometry.
- Subdividing.
- Joining objects.
- Applying booleans.
- Remeshing.
- Rebuilding topology.
- Some modifier applications.

Initial policy:

- Store object pointer.
- Store vertex index.
- Store fallback local coordinate.
- Mark the anchor detached if the vertex index is invalid.

Later recovery policy:

1. Search for a persistent custom vertex ID.
2. Fall back to saved vertex index.
3. Search nearest compatible vertex to fallback local coordinate.
4. If recovery confidence is poor, mark detached.
5. Never silently attach to an obviously wrong vertex.

Possible status display:

```text
● Linked
◐ Recovered
○ Detached
```

---

# Persistent Vertex IDs

Optional future enhancement:

- Add a custom integer attribute on the mesh point domain.
- Assign unique IDs to vertices.
- Store the ID in the anchor.
- Resolve by ID before using index fallback.

Potential field:

```text
persistent_vertex_id
```

Caution:

- Duplication may copy IDs.
- Topology operations may remove IDs.
- Some operations may create duplicate values.
- Modifiers may not preserve source identity.
- Persistent IDs improve recovery but do not guarantee it.

---

# Modifiers

`Scene.ray_cast()` sees evaluated scene geometry.

A modifier-generated vertex may not exist in:

```python
obj.data.vertices
```

Initial policy:

- Snap only to original base-mesh vertices.
- If a ray hit occurs on modifier-generated geometry, inspect whether the corresponding face and vertices map safely to the base mesh.
- Otherwise reject the snap or store an object-local point anchor instead of a vertex anchor.

Recommended visual distinction:

```text
Base vertex: linked snap marker
Modifier result: object-local snap marker
```

Do not pretend a modifier-generated point is permanently linked to a base vertex when it is not.

---

# Object Mode Only

The initial version should work only in Object Mode.

Do not support Edit Mode initially.

Edit Mode introduces:

- BMesh.
- Multi-object editing.
- More complex undo behavior.
- Mesh update timing.
- Selection-state conflicts.
- Topology changes during modal interaction.

Users can create or move vertices in Edit Mode, return to Object Mode, and then create dimensions.

---

# Render Behavior

Initial version:

- Dimensions are viewport-only.
- Dimension Empty objects use `hide_render=True`.

Possible future feature:

```text
Bake Dimensions to Render Objects
```

This could generate:

- Curve objects for dimension lines.
- Mesh arrowheads.
- Text objects for labels.
- A dedicated render collection.
- Camera-facing orientation.
- Emission or unlit materials.

This is not required for the first release.

---

# Recommended File Structure

Begin with a minimal structure:

```text
cad_dimensions/
├── blender_manifest.toml
└── __init__.py
```

After the first prototype works, split into:

```text
cad_dimensions/
├── blender_manifest.toml
├── __init__.py
├── constants.py
├── properties.py
├── collections.py
├── anchors.py
├── snapping.py
├── drawing.py
├── units.py
├── ui.py
├── operators/
│   ├── __init__.py
│   ├── create_dimension.py
│   ├── reattach_anchor.py
│   ├── delete_dimension.py
│   └── select_dimension.py
└── tests/
    └── test_units.py
```

---

# Blender Extension Manifest

Recommended `blender_manifest.toml`:

```toml
schema_version = "1.0.0"

id = "cad_dimensions"
version = "0.1.0"
name = "CAD Dimensions"
tagline = "Persistent vertex-linked dimensions for Blender"
maintainer = "Joseph Mayer"
type = "add-on"

blender_version_min = "4.2.0"

license = [
  "SPDX:GPL-3.0-or-later",
]
```

---

# Minimal Add-on Skeleton

Use this as the first working milestone.

```python
import bpy


DIMENSION_COLLECTION_NAME = "CAD Dimensions"


def get_dimension_collection(context):
    collection = bpy.data.collections.get(DIMENSION_COLLECTION_NAME)

    if collection is None:
        collection = bpy.data.collections.new(DIMENSION_COLLECTION_NAME)
        context.scene.collection.children.link(collection)

    return collection


class CADDIM_OT_AddTestDimension(bpy.types.Operator):
    bl_idname = "caddim.add_test_dimension"
    bl_label = "Add Test Dimension"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = get_dimension_collection(context)

        dimension_object = bpy.data.objects.new(
            "DIM Test",
            object_data=None,
        )

        dimension_object.empty_display_type = "CUBE"
        dimension_object.empty_display_size = 0.1
        dimension_object.hide_render = True
        dimension_object["caddim_kind"] = "DIMENSION"

        collection.objects.link(dimension_object)

        for selected_object in context.selected_objects:
            selected_object.select_set(False)

        dimension_object.select_set(True)
        context.view_layer.objects.active = dimension_object

        self.report({"INFO"}, "Created test dimension object")
        return {"FINISHED"}


class CADDIM_PT_MainPanel(bpy.types.Panel):
    bl_label = "CAD Dimensions"
    bl_idname = "CADDIM_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CAD Dim"

    def draw(self, context):
        layout = self.layout

        layout.label(text="Development Test")
        layout.operator(
            CADDIM_OT_AddTestDimension.bl_idname,
            icon="EMPTY_AXIS",
        )


CLASSES = (
    CADDIM_OT_AddTestDimension,
    CADDIM_PT_MainPanel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
```

Success criterion:

```text
Clicking "Add Test Dimension" creates a selectable "DIM Test" Empty inside a "CAD Dimensions" collection.
```

---

# Development Order

Follow this order exactly.

## Stage 0 — Add-on skeleton

Deliverables:

- Manifest.
- Registration.
- Sidebar tab.
- Test operator.
- Test Empty.
- Dedicated collection.

Acceptance criteria:

- Script runs without error.
- Panel appears.
- Button creates a selectable Empty.
- Empty appears in the correct collection.
- Undo removes it.

## Stage 1 — Persistent properties

Deliverables:

- Anchor PropertyGroup.
- Dimension PropertyGroup.
- PointerProperty attached to Object.
- Start and end anchor data.
- Offset and precision properties.

Acceptance criteria:

- A dimension Empty can store two object pointers and two vertex indices.
- Properties survive saving and reopening the `.blend`.

## Stage 2 — Hard-coded live dimension

Deliverables:

- Resolve two known vertex anchors.
- Draw a line between them.
- Display a numeric label.

Acceptance criteria:

- Move either object.
- The line and value update immediately.

## Stage 3 — CAD graphics

Deliverables:

- Extension lines.
- Main dimension line.
- Arrowheads.
- Centered text.
- Selection color.
- Pixel offset.

Acceptance criteria:

- Zooming does not change text or arrow pixel size.
- Offset remains visually consistent.

## Stage 4 — Vertex hover snapping

Deliverables:

- Modal operator.
- Mouse ray.
- Scene ray cast.
- Hit-face vertex candidates.
- Pixel-distance selection.
- Hover marker.

Acceptance criteria:

- Hover near visible cube corners.
- Correct vertex highlights.
- Works across multiple objects.
- Esc cancels cleanly.

## Stage 5 — Two-click dimension creation

Deliverables:

- Pick start.
- Pick end.
- Set offset.
- Create dimension Empty.
- Store both anchors.

Acceptance criteria:

- Create a dimension across one object.
- Create a dimension across two objects.
- Move either object and verify the dimension follows.

## Stage 6 — Sidebar management

Deliverables:

- Dimension list.
- Selected dimension property panel.
- Rename.
- Hide.
- Delete.
- Show all.
- Hide all.

Acceptance criteria:

- All dimensions are manageable without viewport clicking.

## Stage 7 — Reattach endpoints

Deliverables:

- Reattach Start operator.
- Reattach End operator.
- Anchor replacement.
- Status display.

Acceptance criteria:

- Reattach either endpoint to another object's vertex.
- Dimension updates immediately.

## Stage 8 — Viewport click selection

Deliverables:

- Projected dimension hit testing.
- Line hit test.
- Label hit test.
- Active Empty selection.

Acceptance criteria:

- Clicking near a visible dimension selects its Empty.
- Normal object selection is not globally broken.

## Stage 9 — Imperial fraction formatting

Deliverables:

- Configurable denominator.
- Feet/inches formatting.
- Fraction reduction.
- Rollover handling.

Acceptance criteria:

```text
7.999999 inches -> 8"
11.4375 inches -> 11 7/16"
38.125 inches -> 3' 2 1/8"
```

## Stage 10 — Broken-anchor handling

Deliverables:

- Missing object detection.
- Invalid vertex index detection.
- Warning display.
- Fallback position.
- Optional nearest-vertex recovery.

Acceptance criteria:

- Deleting referenced geometry does not crash Blender.
- Dimension visibly reports a broken anchor.
- Dimension does not silently attach to an obviously wrong point.

## Stage 11 — Polish

Deliverables:

- Preferences.
- Colors.
- Line thickness.
- Text size.
- Arrow style.
- Keymaps.
- Better error reporting.
- Packaging.

---

# Coding Rules

## Prefer direct data access

Prefer:

```python
obj.location.x += 1.0
```

over:

```python
bpy.ops.transform.translate(...)
```

Use operators only when the operation is inherently contextual.

## Never modify scene data from draw callbacks

Draw callbacks may:

- Read data.
- Resolve anchors.
- Compute geometry.
- Draw graphics.

Draw callbacks must not:

- Create objects.
- Delete objects.
- Change selections.
- Change properties.
- Start operators.

## Always remove draw handlers

When unregistering:

```python
bpy.types.SpaceView3D.draw_handler_remove(
    handler,
    "WINDOW",
)
```

Track handler references carefully.

## Separate data from presentation

Dimension objects store data.

Drawing code renders that data.

Snapping code finds candidate anchors.

Operators modify data.

UI code exposes controls.

## Use `PASS_THROUGH` carefully

A modal operator should return `PASS_THROUGH` for events it does not own, so viewport navigation can continue where appropriate.

## Avoid global click interception

Do not leave an always-running modal operator that steals every left click.

Prefer:

- A dedicated tool.
- A dedicated selection mode.
- A modifier click.
- An explicit operator.

## Handle registration order

Register PropertyGroups before classes that use them.

Delete custom PointerProperties before unregistering their PropertyGroup classes.

## Add defensive checks

Check:

- Current area is `VIEW_3D`.
- Current mode is `OBJECT`.
- Target object is a mesh.
- Vertex index is valid.
- Projected screen coordinate is not `None`.
- Draw handler exists before removing it.
- Collection is linked to the current scene.

---

# Testing Scene

Use a trivial scene:

```text
Board_A
Board_B
One dimension
```

Recommended geometry:

- Two cubes.
- Different positions.
- Different scales.
- One rotated object.

Tests:

1. Dimension within one object.
2. Dimension between two objects.
3. Move first object.
4. Move second object.
5. Rotate first object.
6. Scale second object.
7. Move referenced vertex in Edit Mode, then return to Object Mode.
8. Hide one dimension.
9. Delete one dimension.
10. Save and reopen file.
11. Delete referenced vertex.
12. Delete referenced object.
13. Add a modifier and confirm behavior is explicit.

---

# MVP Acceptance Criteria

The first usable release is complete when all of the following work:

- Add-on installs and enables.
- Sidebar panel appears.
- User can create a dimension in Object Mode.
- First and second endpoints can belong to different mesh objects.
- Endpoints link to actual base-mesh vertices.
- Dimension is stored as an Empty.
- Dimension appears in a dedicated collection.
- Dimension survives saving and reopening.
- Dimension updates when either object moves, rotates, or scales.
- Dimension updates when a referenced vertex moves without changing topology.
- Dimension displays extension lines, arrowheads, and a value.
- Dimension can be hidden.
- Dimension can be renamed.
- Dimension can be deleted.
- Dimension properties can be edited.
- Start and end anchors can be reattached.
- Broken references do not crash Blender.
- Imperial fractional display does not produce malformed values such as `7 1/1"`.

The first usable release does not require:

- Global X/Y/Z projected dimensions.
- In-viewport click selection of dimensions.

---

# Explicit Non-Goals for Version 0.1

Do not implement these in the first release:

- Construction guides.
- Tape Measure behavior.
- Geometry-driving dimensions.
- Scaling geometry by editing a dimension.
- Edit Mode picking.
- Angle dimensions.
- Radius or diameter dimensions.
- Renderable dimensions.
- Network synchronization.
- Full modifier-generated topology tracking.
- Guaranteed persistent identity through arbitrary topology changes.
- Virtual snap points.
- Point-to-point move tool.
- Custom transform orientations.
- Constraint solving.
- Parametric CAD behavior.

These may be added after the persistent vertex-linked dimension workflow is stable.

---

# Future Expansion Ideas

After the MVP is reliable:

- Edge endpoint anchors.
- Face anchors using barycentric coordinates.
- Edge midpoint snapping.
- Face-center snapping.
- Bounding-box corner snapping.
- Local-axis dimensions.
- Draggable endpoint gizmos.
- Draggable dimension offset handle.
- Double-click numeric editing.
- Dimension styles.
- Preset arrowheads.
- Render-object baking.
- Persistent vertex IDs.
- Nearest-vertex recovery.
- Geometry-driving dimensions.
- Point-to-point object movement.
- Copy while moving.
- Guide lines and planes.
- Custom transform orientation support.

---

# Suggested Initial Implementation Prompt for Codex

Use the following task statement:

> Create a Blender 4.2+ extension named `CAD Dimensions`. Implement a persistent CAD-style dimension system using one Empty object per dimension and GPU-drawn viewport annotations. The first version must work in Object Mode, allow the user to click two visible base-mesh vertices that may belong to different objects, store each endpoint as an object pointer plus vertex index and fallback local coordinate, and draw a live aligned dimension that updates when either object or referenced vertex moves. Add a `CAD Dim` sidebar panel, a dedicated `CAD Dimensions` collection, a create-dimension modal operator, basic extension lines, arrowheads, label rendering, object-based hide/delete/rename behavior, and explicit start/end reattachment operators. Use defensive error handling, clean draw-handler registration and removal, and do not modify scene data inside draw callbacks. Organize the code into maintainable modules after the initial prototype works. Do not implement Edit Mode, guides, geometry driving, modifier-generated vertex tracking, or renderable dimensions in the first version.

---

# Final Design Principle

The dimension must be treated as a persistent scene entity, not as a temporary ruler.

Its visible graphics are a viewport representation of persistent data.

The persistent data must always remain authoritative:

```text
Dimension Empty
├── Start object
├── Start vertex index
├── Start fallback coordinate
├── End object
├── End vertex index
├── End fallback coordinate
├── Dimension type
├── Offset
├── Precision
├── Visibility
└── Style
```

This architecture provides the best combination of:

- Blender-native object management.
- CAD-like display.
- Cross-object vertex measurement.
- Persistence.
- Editability.
- Extendability.
