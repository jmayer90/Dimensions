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
    "dimensions.create_guide",
)

_MODAL_BINDINGS = (
    ("CONSTRAIN_ALIGNED", "A"),
    ("CONSTRAIN_X", "X"),
    ("CONSTRAIN_Y", "Y"),
    ("CONSTRAIN_Z", "Z"),
    ("CONFIRM", "RET"),
    ("CONFIRM", "NUMPAD_ENTER"),
    ("STEP_BACK", "BACK_SPACE"),
    ("CANCEL", "ESC"),
    ("CANCEL_IMMEDIATE", "RIGHTMOUSE"),
)


class DIMENSIONS_OT_ModalAction(bpy.types.Operator):
    """Carrier for a rebindable modal key.

    The operator is never executed. It exists so a keymap item can name a Dimensions
    modal action in a way the keymap editor can display and rebind.
    """

    bl_idname = "dimensions.modal_action"
    bl_label = "Dimensions Modal Action"
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
    for action, event_type in _MODAL_BINDINGS:
        item = modal_keymap.keymap_items.new("dimensions.modal_action", event_type, "PRESS")
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


def draw_keymaps(layout, context):
    import rna_keymap_ui

    keyconfig = context.window_manager.keyconfigs.user
    if keyconfig is None:
        layout.label(text="Keymap entries are unavailable during registration")
        return
    for keymap, item in registered_keymap_items():
        user_keymap = keyconfig.keymaps.get(keymap.name)
        if user_keymap is None:
            continue
        user_item = user_keymap.keymap_items.from_id(item.id)
        if user_item is None:
            continue
        rna_keymap_ui.draw_kmi([], keyconfig, user_keymap, user_item, layout, 0)


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
        ):
            return configured_item.properties.action
    return None


classes = (DIMENSIONS_OT_ModalAction,)
