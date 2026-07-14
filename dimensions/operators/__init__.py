from .click_select import DIMENSIONS_OT_ClickSelectModal
from .create_dimension import CADDIM_OT_CreateDimension
from .create_guide import CADDIM_OT_ClearGuides, CADDIM_OT_CreateGuide
from .create_line import CADDIM_OT_CreateLine
from .measure import CADDIM_OT_Measure
from .reattach_anchor import CADDIM_OT_ReattachAnchor
from .style import classes as style_classes


classes = (
    DIMENSIONS_OT_ClickSelectModal,
    CADDIM_OT_CreateDimension,
    CADDIM_OT_Measure,
    CADDIM_OT_CreateGuide,
    CADDIM_OT_ClearGuides,
    CADDIM_OT_CreateLine,
    CADDIM_OT_ReattachAnchor,
    *style_classes,
)
