"""Consistent, actionable status-bar messages for Dimensions operators."""


INFO = {"INFO"}
WARNING = {"WARNING"}
ERROR = {"ERROR"}

RUN_FROM_3D_VIEW = "Run this tool from a 3D View"
DIMENSIONS_REQUIRE_SUPPORTED_MODE = "Switch to Object or Mesh Edit Mode to create dimensions"
ANGLE_REQUIRE_SUPPORTED_MODE = "Switch to Object or Mesh Edit Mode to create angle dimensions"
AREA_REQUIRE_SUPPORTED_MODE = "Switch to Object or Mesh Edit Mode to create Area dimensions"
MEASURE_REQUIRE_SUPPORTED_MODE = "Switch to Object or Mesh Edit Mode to measure"
GUIDE_REQUIRE_OBJECT_MODE = "Switch to Object Mode and run this tool from a 3D View"
GUIDE_POINT_REQUIRE_SUPPORTED_MODE = "Switch to Object or Mesh Edit Mode to create a guide point"
GUIDE_POINT_SELECTION_REQUIRED = "Select mesh elements or objects to place a guide point"
REATTACH_REQUIRE_OBJECT_MODE = "Switch to Object Mode to reattach an anchor"
SELECT_DIMENSION_FIRST = "Select a dimension first"
SELECT_ANGLE_DIMENSION = "Select an Angle dimension to remake"
SELECT_AREA_DIMENSION = "Select an Area dimension to remake"
POINT_FIRST_EDGE = "Point at the first mesh edge"
POINT_SECOND_EDGE = "Point at the second mesh edge"
POINT_BASE_MESH_FACE = "Point at a base-mesh face"
SELECT_TWO_NON_PARALLEL_EDGES = "Select two non-parallel edges"
POINT_NON_PARALLEL_EDGES = "Point at two non-parallel, non-degenerate edges"
SELECT_ONE_EDGE = "Select exactly one edge"
SELECT_ONE_OR_MORE_FACES = "Select one or more faces"
SELECT_AREA_BEFORE_SOURCES = "Select an Area annotation before choosing its source faces"
SELECT_AREA_SOURCES = "Select one or more source faces"
AREA_FACES_UNMEASURABLE = "Select faces with measurable area"
AREA_BASE_MESH_REQUIRED = "Choose a face on an object without modifiers"
AREA_SINGLE_OBJECT_REQUIRED = "Choose faces from one object for each Area annotation"
CIRCLE_SELECTION_REQUIRED = "Select at least three mesh vertices, edges, or faces on one object"
CIRCLE_FIT_INVALID = "The selected points cannot define a circle"
CIRCLE_CAPTURE_POOR_FIT = "Improve or repair the circular source before capturing its value"
AREA_SOURCE_INVALID = "Repair the Area source, then create or move its label"
DIFFERENT_END_POINT_REQUIRED = "Choose a different end point"
DIMENSION_OFFSET_PLANE_REQUIRED = "Adjust the view and choose two distinct points before placing the dimension"
GUIDE_DIRECTION_DISTANCE_REQUIRED = "Choose a direction and a non-zero guide distance"
MEASUREMENT_DIRECTION_DISTANCE_REQUIRED = "Choose a direction and a non-zero measurement distance"
RESET_GLOBAL_STYLE = "Reset selected dimension to the global style"
COPIED_GLOBAL_STYLE = "Copied selected dimension style to global defaults"
CLEARED_STYLE_OVERRIDES = "Cleared local style overrides"
LINKED_STYLE_USERS = "Make linked annotations local before renaming or deleting their style"
MANAGER_ITEM_MISSING = "Refresh the annotation manager and choose an existing item"
MANAGER_LINKED_READ_ONLY = "Make the linked annotation local before changing it"
DELETED_ANNOTATION = "Deleted annotation"
REPAIR_SOURCES_SELECTED = "Selected the annotation and its available source objects"
REPAIR_NOT_REQUIRED = "This annotation has no broken or fallback source"
REPAIR_NO_SUGGESTION = "No safe candidate is available; pick a replacement manually"
REPAIR_SOURCE_GONE = "Only an unresolvable anchor can be converted to a world point"
REPAIR_LINKED_READ_ONLY = "Make the linked annotation local before repairing it"
REPAIR_PICK_BASE_FACE = "Point at the replacement base-mesh face"
HANDLE_NO_LONGER_AVAILABLE = "Select the annotation again and choose its visible handle"
MANAGER_ISOLATE_RESTORED = "Restored annotation visibility from before isolate"
MANAGER_STYLE_REQUIRED = "Create or choose a named style before applying it"
CREATED_SELECTED_EDGE = "Created dimension from selected edge"
CREATED_AREA_ANNOTATION = "Created area annotation from selected faces"
CAPTURED_AREA_VALUE = "Captured Area value"
SELECTED_BOUND_FACES = "Selected bound source faces"
CREATED_SELECTED_ANGLE = "Created angle dimension from selected edges"
CREATED_DIMENSION = "Created dimension"
CREATED_CIRCLE_DIMENSION = "Created circular dimension"
CAPTURED_CIRCLE_VALUE = "Captured circular dimension value"
CREATED_GUIDE = "Created construction guide"
CREATED_GUIDE_POINT = "Created guide point"
CREATED_DATUM = "Created named datum"
CREATED_COORDINATE = "Created coordinate dimension"
CREATED_ELEVATION = "Created elevation dimension"
DATUM_REQUIRED = "Create or select a named datum first"
CREATED_DERIVED_GUIDE = "Created derived guide"
DERIVED_GUIDE_PARALLEL_REQUIRED = "Choose a second source parallel to the first"
SELECT_DERIVED_GUIDE = "Select a live derived guide first"
DETACHED_DERIVED_GUIDE = "Detached derived guide"
DERIVED_GUIDE_CYCLE_REFUSED = "Choose a source that does not depend on this guide"
REATTACHED_DERIVED_GUIDE_SOURCE = "Reattached derived guide source"
CREATED_MEASUREMENT = "Created persistent measurement"
SAVED_TRANSIENT_MEASUREMENT = "Saved transient measurement"
COPIED_TRANSIENT_MEASUREMENT = "Copied measurement to clipboard"
MEASUREMENT_REQUIRED_TO_SAVE = "Acquire a non-zero measurement before saving or copying"
OUTPUT_NO_LINEAR_ANNOTATIONS = "No visible linear annotations match the output scope"
OUTPUT_NO_ANNOTATIONS = "No visible annotations match the output scope"
OUTPUT_CAMERA_REQUIRED = "Set an active camera for Camera Relative output sizing"
OUTPUT_NO_VALID_LINEAR_ANNOTATIONS = "No valid linear annotations could be generated"
OUTPUT_NO_VALID_ANNOTATIONS = "No valid annotations could be generated"
OUTPUT_AREA_REPAIR_REQUIRED = "Repair skipped Area sources before generating output"
VECTOR_CAMERA_REQUIRED = "Set an active camera before exporting SVG or PDF"
VECTOR_NO_VALID_ANNOTATIONS = "No valid visible annotations are available for vector export"


def invalid_distance(value):
    return f"Enter a valid distance instead of {value!r}"


def extension_axis(axis_label):
    return f"Extension axis: {axis_label}"


def guide_direction(axis_label):
    return f"Guide direction: {axis_label}"


def measurement_direction(axis_label):
    return f"Measurement direction: {axis_label}"


def created_area(face_count, remade=False):
    action = "Remade" if remade else "Created"
    return f"{action} Area from {face_count} face(s)"


def created_angle(remade=False):
    action = "Remade" if remade else "Created"
    return f"{action} two-edge angle dimension"


def rebound_area(face_count):
    return f"Rebound Area to {face_count} face(s)"


def reattached_anchor(anchor_name):
    return f"Reattached {anchor_name.lower()} anchor"


def repair_explanation(issue):
    state = "uses its stored fallback" if issue["status"] == "BY_FALLBACK" else "lost its source"
    return f"{issue['type'].title()} {state} on {issue['source_name']!r}"


def accepted_repairs(count):
    return f"Accepted {count} suggested repair(s)"


def converted_anchor(anchor_name):
    return f"Converted {anchor_name.lower()} to a fixed world point"


def adjusted_handle(handle_kind):
    return f"Adjusted {handle_kind.lower().replace('_', ' ')}"


def applied_global_style(count):
    return f"Applied global style to {count} dimension(s)"


def created_style(name):
    return f"Created annotation style {name!r}"


def renamed_style(name):
    return f"Renamed annotation style to {name!r}"


def deleted_style(name, reassigned):
    return f"Deleted {name!r}; {reassigned} annotation(s) now use scene defaults"


def assigned_style(name, count):
    return f"Assigned {name!r} to {count} selected annotation(s)"


def selected_style_users(name, count):
    return f"Selected {count} annotation(s) using {name!r}"


def renamed_annotation(name):
    return f"Renamed annotation to {name!r}"


def manager_bulk_changed(count):
    return f"Updated visibility for {count} managed item(s)"


def manager_deleted(count):
    return f"Deleted {count} managed item(s)"


def cleared_guides(count):
    return f"Removed {count} construction guide(s)"


def cleared_measurements(count):
    return f"Removed {count} measurement(s)"


def generated_output(generated, skipped=0, skipped_repair=0):
    message = f"Generated Grease Pencil output for {generated} annotation(s)"
    if skipped:
        message += f"; skipped {skipped} unavailable annotation(s)"
    if skipped_repair:
        message += "; repair skipped Area source(s)"
    return message


def exported_vector(format_label, exported, skipped=0):
    message = f"Exported {exported} annotation(s) to {format_label}"
    if skipped:
        message += f"; skipped {skipped} fallback or repair annotation(s)"
    return message


def vector_export_failed(detail):
    return f"Vector export failed: {detail}"


CREATED_GUIDE_PLANE = "Created guide plane"
GUIDE_PLANE_DEFINITION_INVALID = "Choose a valid non-degenerate plane definition"
SELECT_GUIDE_PLANE = "Select a live guide plane"
SELECT_FACE_FOR_PLANE = "Select a mesh face for the construction plane"
ACTIVE_GUIDE_PLANE_SET = "Active construction plane set from guide plane"
ACTIVE_FACE_PLANE_SET = "Active construction plane set from face"
ACTIVE_WORLD_PLANE_SET = "Active construction plane set from world plane"
ACTIVE_VIEW_PLANE_SET = "Active construction plane set from current view"
ACTIVE_PLANE_CLEARED = "Cleared active construction plane"
GUIDE_PLANE_REPAIRED = "Repaired guide plane source"
GUIDE_PLANE_REPAIR_INVALID = "Pick a compatible source that defines a live plane"
AREA_MODIFIER_IDENTITY_UNRESOLVED = "Modifier faces lack unique source IDs; disable the modifier or capture the base value"


def guide_plane_repair_points(count):
    return f"Picked {count} of 3 replacement plane points"
SELECT_GUIDE_SOURCE = "Select an existing guide or guide plane first"
DERIVED_GUIDE_SOURCE_REQUIRED = "The selected construction source cannot resolve"
SELECT_SPACING_GUIDE = "Select an editable repeated-spacing guide set first"
CREATED_ANGULAR_GUIDE = "Created angular guide"
CREATED_SPACING_GUIDE = "Created repeated-spacing guide set"
BAKED_SPACING_GUIDE = "Baked {count} individual guides"
