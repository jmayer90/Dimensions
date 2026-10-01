from .click_select import DIMENSIONS_OT_ClickSelect
from .create_dimension import CADDIM_OT_CreateDimension
from .create_angle import DIMENSIONS_OT_CreateAngle, DIMENSIONS_OT_ReplaceAngleEdge
from .create_area import DIMENSIONS_OT_CreateArea, DIMENSIONS_OT_MoveAreaLabel
from .construction_tools import classes as construction_classes
from .measure import CADDIM_OT_Measure, CADDIM_OT_PersistentMeasure
from .generate_output import DIMENSIONS_OT_GenerateOutput
from .export_vector import classes as vector_export_classes
from .reattach_anchor import CADDIM_OT_ReattachAnchor
from .style import classes as style_classes
from .annotation_manager import classes as annotation_manager_classes
from .repair import classes as repair_classes
from .drag_handle import classes as handle_classes
from .selection_annotations import classes as selection_annotation_classes


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
    *construction_classes,
    CADDIM_OT_ReattachAnchor,
    *selection_annotation_classes,
    *style_classes,
    *annotation_manager_classes,
    *repair_classes,
    *handle_classes,
)
