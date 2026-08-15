"""A fake 3D viewport context and event source for headless modal tests."""

from mathutils import Matrix, Quaternion, Vector


class FakeRegion:
    def __init__(self, width=1920, height=1080, region_type="WINDOW"):
        self.width = width
        self.height = height
        self.type = region_type

    def as_pointer(self):
        return id(self)

    def tag_redraw(self):
        pass


class FakeRegionData:
    """Stands in for ``RegionView3D`` with an orthographic top-down view by default."""

    def __init__(self, view_rotation=None, view_distance=10.0, perspective_matrix=None):
        self.view_rotation = Quaternion() if view_rotation is None else view_rotation
        self.view_distance = view_distance
        self.perspective_matrix = (
            Matrix.Identity(4) if perspective_matrix is None else perspective_matrix
        )
        self.view_matrix = Matrix.Identity(4)
        self.is_perspective = False

    def as_pointer(self):
        return id(self)


class FakeArea:
    def __init__(self, area_type="VIEW_3D", regions=None):
        self.type = area_type
        self.regions = regions or []

    def as_pointer(self):
        return id(self)

    def tag_redraw(self):
        pass


class FakeWindow:
    def __init__(self, screen=None):
        self.screen = screen

    def as_pointer(self):
        return id(self)


class FakeContext:
    """Minimum viable ``bpy.context`` for the parts of the draw and modal paths under test."""

    def __init__(self, scene=None, mode="OBJECT", area=None, region=None, region_data=None):
        self.region = FakeRegion() if region is None else region
        self.region_data = FakeRegionData() if region_data is None else region_data
        self.area = FakeArea(regions=[self.region]) if area is None else area
        self.window = FakeWindow()
        self.scene = scene
        self.mode = mode
        self.selected_objects = []
        self.view_layer = None
        self.space_data = None


class FakeEvent:
    """Stands in for a Blender modal event."""

    def __init__(
        self,
        event_type="MOUSEMOVE",
        value="PRESS",
        mouse_region_x=0,
        mouse_region_y=0,
        ascii_character="",
    ):
        self.type = event_type
        self.value = value
        self.mouse_region_x = mouse_region_x
        self.mouse_region_y = mouse_region_y
        self.ascii = ascii_character
        self.shift = False
        self.ctrl = False
        self.alt = False


def make_context(**kwargs):
    return FakeContext(**kwargs)


def make_event(event_type="MOUSEMOVE", value="PRESS", **kwargs):
    return FakeEvent(event_type=event_type, value=value, **kwargs)


def typing_events(text):
    """Return one PRESS event per character, as Blender delivers typed input."""
    return [make_event("TEXTINPUT", "PRESS", ascii_character=character) for character in text]


def world_point(x=0.0, y=0.0, z=0.0):
    return Vector((x, y, z))
