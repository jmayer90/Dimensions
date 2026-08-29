from .click_select import DIMENSIONS_OT_ClickSelect
from .create_dimension import CADDIM_OT_CreateDimension
from .create_angle import DIMENSIONS_OT_CreateAngle, DIMENSIONS_OT_ReplaceAngleEdge
from .create_area import DIMENSIONS_OT_CreateArea, DIMENSIONS_OT_MoveAreaLabel
from .create_guide import CADDIM_OT_ClearGuides, CADDIM_OT_ClearMeasurements, CADDIM_OT_CreateGuide
from .create_guide_point import classes as guide_point_classes
from .offset_guide import classes as offset_guide_classes
from .measure import CADDIM_OT_Measure, CADDIM_OT_PersistentMeasure
from .generate_output import DIMENSIONS_OT_GenerateOutput
from .export_vector import classes as vector_export_classes
from .reattach_anchor import CADDIM_OT_ReattachAnchor
from .style import classes as style_classes
from .annotation_manager import classes as annotation_manager_classes
from .repair import classes as repair_classes
from .drag_handle import classes as handle_classes
from .dimension_set import classes as dimension_set_classes
from .create_circle import classes as circle_classes
from .selection_annotations import classes as selection_annotation_classes
from .create_coordinate import classes as coordinate_classes
from .guide_plane import classes as guide_plane_classes
from .angular_spacing import classes as angular_spacing_classes


classes = (
    DIMENSIONS_OT_ClickSelect,
    CADDIM_OT_CreateDimension,
    DIMENSIONS_OT_CreateAngle,
    DIMENSIONS_OT_ReplaceAngleEdge,
    DIMENSIONS_OT_CreateArea,
    DIMENSIONS_OT_MoveAreaLabel,
    CADDIM_OT_Measure,
    CADDIM_OT_PersistentMeasure,
    DIMENSIONS_OT_GenerateOutput,
    *vector_export_classes,
    CADDIM_OT_CreateGuide,
    *guide_point_classes,
    *offset_guide_classes,
    CADDIM_OT_ClearGuides,
    CADDIM_OT_ClearMeasurements,
    CADDIM_OT_ReattachAnchor,
    *selection_annotation_classes,
    *style_classes,
    *annotation_manager_classes,
    *repair_classes,
    *handle_classes,
    *dimension_set_classes,
    *circle_classes,
    *coordinate_classes,
    *guide_plane_classes,
    *angular_spacing_classes,
)
