"""Deliberate transform semantics for annotation locator objects."""

from mathutils import Vector


IDENTITY_SCALE = Vector((1.0, 1.0, 1.0))


def enforce_annotation_transform_policy(annotation):
    """Lock unsupported channels without rewriting legacy object transforms.

    Annotation location is the only Blender transform channel with product
    meaning: scene synchronization converts its world-space delta from the
    canonical source frame into ``presentation_offset``. Rotation and scale are
    never measurement or presentation inputs, so normal Blender transform tools
    are prevented from editing those channels. Existing values are retained to
    avoid changing saved Empty appearance; drawing and output continue to ignore
    them.
    """
    changed = False
    rotation_lock = (True, True, True)
    scale_lock = (True, True, True)
    if tuple(annotation.lock_rotation) != rotation_lock:
        annotation.lock_rotation = rotation_lock
        changed = True
    if tuple(annotation.lock_scale) != scale_lock:
        annotation.lock_scale = scale_lock
        changed = True
    return changed


def annotation_world_location(annotation):
    """Return the one transform component permitted to affect presentation."""
    return (
        Vector(annotation.location)
        if annotation.parent is None
        else annotation.matrix_world.translation.copy()
    )


def has_ignored_rotation_or_scale(annotation, epsilon=1e-6):
    """Report legacy/scripted unsupported channels for UI explanation and tests."""
    scale = Vector(annotation.scale)
    if (scale - IDENTITY_SCALE).length > epsilon:
        return True
    mode = annotation.rotation_mode
    if mode == "QUATERNION":
        quaternion = annotation.rotation_quaternion
        return abs(quaternion.angle) > epsilon
    if mode == "AXIS_ANGLE":
        return abs(float(annotation.rotation_axis_angle[0])) > epsilon
    return Vector(annotation.rotation_euler).length > epsilon
