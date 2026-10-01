"""Drive a modal operator's Python logic without instantiating a ``bpy`` operator.

Blender refuses to construct operator types from Python, so the tests cannot simply
call ``CADDIM_OT_CreateDimension()``. The harness rebuilds a plain class from the
operator's own functions, properties, and class attributes — including those it
inherits from shared Dimensions base classes — which keeps the code under test
identical to the shipped code while making it constructible in a background session.
"""


def _is_blender_class(klass):
    return klass is object or klass.__module__.startswith(("bpy", "_bpy"))


def make_operator_harness(operator_class, **attributes):
    """Return an instance exposing ``operator_class``'s methods and properties.

    Reported messages accumulate on ``harness.reports`` as ``(severity, message)``
    so tests can assert that a refused stage told the user how to correct it.
    """
    namespace = {}
    for klass in reversed(operator_class.__mro__):
        if _is_blender_class(klass):
            continue
        for name, value in vars(klass).items():
            if name.startswith("__") or name.startswith("bl_"):
                continue
            namespace[name] = value
    harness_class = type(f"{operator_class.__name__}Harness", (object,), namespace)
    harness = harness_class()
    harness.reports = []
    harness.report = lambda severity, message: harness.reports.append((severity, message))
    for name, value in attributes.items():
        setattr(harness, name, value)
    return harness
