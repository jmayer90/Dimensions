import bpy

from ..drawing import find_dimension_hit, find_guide_hit
from ..viewport_state import prune_stale_states


_click_select_timer_active = False


def register_click_select():
    global _click_select_timer_active

    if _click_select_timer_active:
        return

    _click_select_timer_active = True
    if not bpy.app.timers.is_registered(_ensure_click_select_running):
        bpy.app.timers.register(_ensure_click_select_running, first_interval=0.2)


def unregister_click_select():
    global _click_select_timer_active
    _click_select_timer_active = False
    if bpy.app.timers.is_registered(_ensure_click_select_running):
        bpy.app.timers.unregister(_ensure_click_select_running)
    DIMENSIONS_OT_ClickSelectModal._running_areas.clear()


def _ensure_click_select_running():
    if not _click_select_timer_active:
        return None

    prune_stale_states()
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue

        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue

            window_region = next((region for region in area.regions if region.type == "WINDOW"), None)
            if window_region is None:
                continue

            area_key = (window.as_pointer(), area.as_pointer())
            if area_key in DIMENSIONS_OT_ClickSelectModal._running_areas:
                continue

            with bpy.context.temp_override(window=window, area=area, region=window_region):
                try:
                    bpy.ops.dimensions.click_select_modal("INVOKE_DEFAULT")
                except RuntimeError:
                    continue

    return 1.0


class DIMENSIONS_OT_ClickSelectModal(bpy.types.Operator):
    bl_idname = "dimensions.click_select_modal"
    bl_label = "Dimensions Click Select"
    bl_options = {"INTERNAL"}

    _running_areas = set()

    def invoke(self, context, _event):
        if context.area is None or context.area.type != "VIEW_3D":
            return {"CANCELLED"}

        area_key = (context.window.as_pointer(), context.area.as_pointer())
        if area_key in self.__class__._running_areas:
            return {"CANCELLED"}

        self._area_key = area_key
        self.__class__._running_areas.add(area_key)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not _click_select_timer_active:
            self._cleanup()
            return {"CANCELLED"}

        if context.area is None or context.area.type != "VIEW_3D":
            self._cleanup()
            return {"CANCELLED"}

        if context.region is None or context.region.type != "WINDOW":
            return {"PASS_THROUGH"}

        settings = getattr(context.scene, "dimensions_settings", None)
        if settings is None or not settings.enable_click_select or context.mode != "OBJECT":
            return {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            hit_object = find_dimension_hit(
                context,
                event.mouse_region_x,
                event.mouse_region_y,
            )
            if hit_object is None:
                hit_object = find_guide_hit(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                )
                if hit_object is None:
                    return {"PASS_THROUGH"}

            if event.shift:
                hit_object.select_set(not hit_object.select_get())
                if hit_object.select_get():
                    context.view_layer.objects.active = hit_object
                elif context.view_layer.objects.active == hit_object:
                    remaining = list(context.selected_objects)
                    context.view_layer.objects.active = remaining[-1] if remaining else None
            else:
                for selected_object in context.selected_objects:
                    selected_object.select_set(False)
                hit_object.select_set(True)
                context.view_layer.objects.active = hit_object

            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        return {"PASS_THROUGH"}

    def cancel(self, _context):
        self._cleanup()

    def _cleanup(self):
        area_key = getattr(self, "_area_key", None)
        if area_key is not None:
            self.__class__._running_areas.discard(area_key)
