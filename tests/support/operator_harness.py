"""Drive a modal operator's Python logic without instantiating a ``bpy`` operator.

Blender refuses to construct operator types from Python, so the tests cannot simply
call ``CADDIM_OT_CreateDimension()``. The harness rebuilds a plain class from the
operator's own functions and properties, which keeps the code under test identical
to the shipped code while making it constructible in a background session.
"""


def make_operator_harness(operator_class, **attributes):
    """Return an instance exposing ``operator_class``'s methods and properties.

    Reported messages accumulate on ``harness.reports`` as ``(severity, message)``
    so tests can assert that a refused stage told the user how to correct it.
    """
    namespace = {
        name: value
        for name, value in vars(operator_class).items()
        if callable(value) or isinstance(value, (property, staticmethod, classmethod))
    }
    harness_class = type(f"{operator_class.__name__}Harness", (object,), namespace)
    harness = harness_class()
    harness.reports = []
    harness.report = lambda severity, message: harness.reports.append((severity, message))
    for name, value in attributes.items():
        setattr(harness, name, value)
    return harness
