"""Add-on-owned invocation keymaps with leak-free lifecycle management.

Blender refuses modal key-maps in an add-on key configuration, so the modal keys are
kept in a private action map instead: a Dimensions-owned keymap whose items carry an
action name and are never dispatched by Blender. ``modal_action_from_event`` reads that
map through the *user* key configuration, which is what makes rebinding in the keymap
editor take effect immediately and without a restart.
"""

import bpy


_keymap_items = []
_modal_keymap_items = []


MODAL_KEYMAP_NAME = "Dimensions Modal"
INVOCATION_KEYMAP_NAME = "3D View"

_INVOCATION_OPERATORS = (
    "dimensions.create_dimension",
    "dimensions.create_angle",
    "dimensions.create_area",
    "dimensions.measure",
    "dimensions.measure_persistent",
    "dimensions.create_guide",
    "dimensions.create_guide_point",
    "dimensions.create_offset_guide",
    "dimensions.create_guide_plane",
)

_MODAL_BINDINGS = (
    ("CONSTRAIN_ALIGNED", "A"),
    ("CONSTRAIN_X", "X"),
    ("CONSTRAIN_Y", "Y"),
    ("CONSTRAIN_Z", "Z"),
    ("CONFIRM", "RET"),
    ("CONFIRM", "NUMPAD_ENTER"),
    ("CYCLE_SNAP_TARGETS", "S"),
    ("TOGGLE_INFERENCE_LOCK", "L"),
    ("SAVE_TRANSIENT_MEASURE", "P"),
    ("COPY_TRANSIENT_MEASURE", "C", {"ctrl": True}),
)


class DIMENSIONS_OT_ModalAction(bpy.types.Operator):
    """Carrier for a rebindable modal key.

    The operator is never executed. It exists so a keymap item can name a Dimensions
    modal action in a way the keymap editor can display and rebind.
    """

    bl_idname = "dimensions.modal_action"
    bl_label = "Dimensions Modal Action"
    bl_description = "A key that Dimensions tools respond to while they run; rebind it to change the key"
    bl_options = {"INTERNAL"}

    action: bpy.props.StringProperty(name="Action", default="")

    def execute(self, _context):
        return {"CANCELLED"}


def register_keymaps():
    if _keymap_items:
        return
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is None:
        return

    # Invocation entries are registered unbound so they can never collide with a
    # default Blender binding. They appear in the keymap editor for users to bind.
    keymap = keyconfig.keymaps.new(name=INVOCATION_KEYMAP_NAME, space_type="VIEW_3D")
    for operator_id in _INVOCATION_OPERATORS:
        item = keymap.keymap_items.new(operator_id, "NONE", "PRESS")
        item.active = False
        _keymap_items.append((keymap, item))

    modal_keymap = keyconfig.keymaps.new(name=MODAL_KEYMAP_NAME, space_type="EMPTY")
    for binding in _MODAL_BINDINGS:
        action, event_type = binding[:2]
        modifiers = binding[2] if len(binding) > 2 else {}
        item = modal_keymap.keymap_items.new(
            "dimensions.modal_action", event_type, "PRESS", **modifiers
        )
        item.properties.action = action
        _modal_keymap_items.append((modal_keymap, item))


def unregister_keymaps():
    modal_keymaps = {keymap for keymap, _item in _modal_keymap_items}
    while _modal_keymap_items:
        keymap, item = _modal_keymap_items.pop()
        try:
            keymap.keymap_items.remove(item)
        except (ReferenceError, RuntimeError):
            pass
    while _keymap_items:
        keymap, item = _keymap_items.pop()
        try:
            keymap.keymap_items.remove(item)
        except (ReferenceError, RuntimeError):
            pass

    # The private action map is ours alone, so the container goes too — leaving an
    # empty "Dimensions Modal" entry behind would survive disabling the add-on.
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is None:
        return
    for keymap in modal_keymaps:
        try:
            keyconfig.keymaps.remove(keymap)
        except (ReferenceError, RuntimeError, TypeError):
            pass


def registered_keymap_items():
    """Every item this add-on owns, for the preferences UI and the collision test."""
    return tuple((*_keymap_items, *_modal_keymap_items))


_ACTION_LABELS = {
    "CONSTRAIN_ALIGNED": "Auto Direction",
    "CONSTRAIN_X": "Lock X",
    "CONSTRAIN_Y": "Lock Y",
    "CONSTRAIN_Z": "Lock Z",
    "CONFIRM": "Confirm",
    "CYCLE_SNAP_TARGETS": "Cycle Snap Targets",
    "TOGGLE_INFERENCE_LOCK": "Lock Inference Reference",
    "SAVE_TRANSIENT_MEASURE": "Save Measurement",
    "COPY_TRANSIENT_MEASURE": "Copy Measurement",
}


def _user_item(keyconfig, keymap, item):
    user_keymap = keyconfig.keymaps.get(keymap.name)
    if user_keymap is None:
        return None, None
    return user_keymap, user_keymap.keymap_items.from_id(item.id)


def draw_keymaps(layout, context):
    import rna_keymap_ui

    keyconfig = context.window_manager.keyconfigs.user
    if keyconfig is None:
        layout.label(text="Keymap entries are unavailable during registration")
        return
    layout.label(text="Start a tool (unbound until you assign a key)")
    for keymap, item in _keymap_items:
        user_keymap, user_item = _user_item(keyconfig, keymap, item)
        if user_item is not None:
            rna_keymap_ui.draw_kmi([], keyconfig, user_keymap, user_item, layout, 0)
    layout.separator()
    layout.label(text="While a tool runs")
    # Every modal key shares one carrier operator, so Blender's own row would label
    # them all "Dimensions Modal Action"; name each by its action instead.
    column = layout.column(align=True)
    for keymap, item in _modal_keymap_items:
        _user_keymap, user_item = _user_item(keyconfig, keymap, item)
        if user_item is None:
            continue
        action = user_item.properties.action
        row = column.row(align=True)
        row.prop(user_item, "active", text="")
        row.label(text=_ACTION_LABELS.get(action, action.replace("_", " ").title()))
        row.prop(user_item, "type", text="", full_event=True)


def modal_action_from_event(event):
    try:
        user_keyconfig = bpy.context.window_manager.keyconfigs.user
    except (AttributeError, RuntimeError):
        user_keyconfig = None
    for keymap, item in _modal_keymap_items:
        configured_item = item
        if user_keyconfig is not None:
            user_keymap = user_keyconfig.keymaps.get(keymap.name)
            if user_keymap is not None:
                configured_item = user_keymap.keymap_items.from_id(item.id) or item
        if (
            configured_item.active
            and configured_item.type == event.type
            and configured_item.value == event.value
            and bool(configured_item.shift) == bool(getattr(event, "shift", False))
            and bool(configured_item.ctrl) == bool(getattr(event, "ctrl", False))
            and bool(configured_item.alt) == bool(getattr(event, "alt", False))
        ):
            return configured_item.properties.action
    return None


classes = (DIMENSIONS_OT_ModalAction,)
