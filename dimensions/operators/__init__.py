from .click_select import DIMENSIONS_OT_ClickSelectModal
from .create_dimension import CADDIM_OT_CreateDimension
from .reattach_anchor import CADDIM_OT_ReattachAnchor
from .style import classes as style_classes


classes = (
    DIMENSIONS_OT_ClickSelectModal,
    CADDIM_OT_CreateDimension,
    CADDIM_OT_ReattachAnchor,
    *style_classes,
)
