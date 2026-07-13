import bpy

from .constants import (
    DEFAULT_EMPTY_DISPLAY_SIZE,
    DEFAULT_EMPTY_DISPLAY_TYPE,
    DIMENSION_COLLECTION_NAME,
)


def get_or_create_dimension_collection(context):
    collection = bpy.data.collections.get(DIMENSION_COLLECTION_NAME)

    if collection is None:
        collection = bpy.data.collections.new(DIMENSION_COLLECTION_NAME)

    scene_children = context.scene.collection.children
    if scene_children.get(collection.name) is None:
        scene_children.link(collection)

    return collection


def create_dimension_object(context, name="DIM Dimension"):
    collection = get_or_create_dimension_collection(context)

    dimension_object = bpy.data.objects.new(name, object_data=None)
    dimension_object.empty_display_type = DEFAULT_EMPTY_DISPLAY_TYPE
    dimension_object.empty_display_size = DEFAULT_EMPTY_DISPLAY_SIZE
    dimension_object.hide_render = True

    collection.objects.link(dimension_object)

    if hasattr(dimension_object, "dimension_props"):
        dimension_object.dimension_props.enabled = True

    return dimension_object
