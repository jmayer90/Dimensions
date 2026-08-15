from .click_select import DIMENSIONS_OT_ClickSelect
from .create_dimension import CADDIM_OT_CreateDimension
from .create_angle import DIMENSIONS_OT_CreateAngle, DIMENSIONS_OT_ReplaceAngleEdge
from .create_area import DIMENSIONS_OT_CreateArea, DIMENSIONS_OT_MoveAreaLabel
from .create_guide import CADDIM_OT_ClearGuides, CADDIM_OT_ClearMeasurements, CADDIM_OT_CreateGuide
from .measure import CADDIM_OT_Measure
from .reattach_anchor import CADDIM_OT_ReattachAnchor
from .style import classes as style_classes
from .selection_annotations import classes as selection_annotation_classes


classes = (
    DIMENSIONS_OT_ClickSelect,
    CADDIM_OT_CreateDimension,
    DIMENSIONS_OT_CreateAngle,
    DIMENSIONS_OT_ReplaceAngleEdge,
    DIMENSIONS_OT_CreateArea,
    DIMENSIONS_OT_MoveAreaLabel,
    CADDIM_OT_Measure,
    CADDIM_OT_CreateGuide,
    CADDIM_OT_ClearGuides,
    CADDIM_OT_ClearMeasurements,
    CADDIM_OT_ReattachAnchor,
    *selection_annotation_classes,
    *style_classes,
)
