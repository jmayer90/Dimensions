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
AREA_SOURCE_INVALID = "Repair the Area source, then create or move its label"
DIFFERENT_END_POINT_REQUIRED = "Choose a different end point"
DIMENSION_OFFSET_PLANE_REQUIRED = "Adjust the view and choose two distinct points before placing the dimension"
GUIDE_DIRECTION_DISTANCE_REQUIRED = "Choose a direction and a non-zero guide distance"
MEASUREMENT_DIRECTION_DISTANCE_REQUIRED = "Choose a direction and a non-zero measurement distance"
RESET_GLOBAL_STYLE = "Reset selected dimension to the global style"
COPIED_GLOBAL_STYLE = "Copied selected dimension style to global defaults"
CREATED_SELECTED_EDGE = "Created dimension from selected edge"
CREATED_AREA_ANNOTATION = "Created area annotation from selected faces"
CAPTURED_AREA_VALUE = "Captured Area value"
SELECTED_BOUND_FACES = "Selected bound source faces"
CREATED_SELECTED_ANGLE = "Created angle dimension from selected edges"
CREATED_DIMENSION = "Created dimension"
CREATED_GUIDE = "Created construction guide"
CREATED_MEASUREMENT = "Created persistent measurement"
OUTPUT_NO_LINEAR_ANNOTATIONS = "No visible linear annotations match the output scope"
OUTPUT_NO_ANNOTATIONS = "No visible annotations match the output scope"
OUTPUT_CAMERA_REQUIRED = "Set an active camera for Camera Relative output sizing"
OUTPUT_NO_VALID_LINEAR_ANNOTATIONS = "No valid linear annotations could be generated"
OUTPUT_NO_VALID_ANNOTATIONS = "No valid annotations could be generated"
OUTPUT_AREA_REPAIR_REQUIRED = "Repair skipped Area sources before generating output"


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


def applied_global_style(count):
    return f"Applied global style to {count} dimension(s)"


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
