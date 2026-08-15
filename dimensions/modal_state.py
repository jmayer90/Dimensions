"""Pure stage transitions shared by modal annotation operators and their tests.

The operators keep their viewport queries and scene side effects. Everything that the
interaction contract promises — which stage a tool is in, when typed input and axis
locks are accepted, and what escape and step-back do — lives here so it can be driven
without a window and stays identical across tools.
"""


class PointPlacementState:
    """Model pick-start, pick-end, placement, axis locking, and numeric entry."""

    PICK_START = "PICK_START"
    PICK_END = "PICK_END"
    PLACE = "SET_OFFSET"

    DEFAULT_AXIS = "ALIGNED"

    def __init__(self, placement_stage=PLACE):
        self.placement_stage = placement_stage
        self.stage = self.PICK_START
        self.numeric_text = ""
        self.numeric_valid = True
        self.axis = self.DEFAULT_AXIS

    # -- queries ---------------------------------------------------------

    @property
    def accepts_numeric_input(self):
        """Typed distances are offered once a first point exists."""
        return self.stage in (self.PICK_END, self.placement_stage)

    @property
    def accepts_axis_lock(self):
        """An axis constrains the placement stage, so it is only taken there."""
        return self.stage == self.placement_stage

    @property
    def has_pending_numeric_input(self):
        return bool(self.numeric_text.strip())

    # -- transitions -----------------------------------------------------

    def accept_point(self):
        if self.stage == self.PICK_START:
            self.stage = self.PICK_END
            self.clear_numeric()
            return "PICK_START_ACCEPTED"
        if self.stage == self.PICK_END:
            self.stage = self.placement_stage
            self.clear_numeric()
            return "PICK_END_ACCEPTED"
        return "NO_ACTION"

    def set_numeric_text(self, text, valid=True):
        self.numeric_text = text
        self.numeric_valid = True if not text.strip() else bool(valid)
        return "NUMERIC_UPDATED"

    def clear_numeric(self):
        self.numeric_text = ""
        self.numeric_valid = True

    def set_axis(self, axis):
        if axis is None:
            return "NO_ACTION"
        if not self.accepts_axis_lock:
            return "AXIS_IGNORED"
        self.axis = axis
        return "AXIS_SET"

    def confirm(self):
        """Advance a picking stage, or commit from the placement stage."""
        if self.stage in (self.PICK_START, self.PICK_END):
            return self.accept_point()
        if self.has_pending_numeric_input and not self.numeric_valid:
            return "NUMERIC_INVALID"
        return "COMMITTED"

    def escape(self):
        if self.numeric_text:
            self.clear_numeric()
            return "NUMERIC_CLEARED"
        return self.step_back()

    def step_back(self):
        self.clear_numeric()
        if self.stage == self.placement_stage:
            self.stage = self.PICK_END
            return "STEPPED_BACK"
        if self.stage == self.PICK_END:
            self.stage = self.PICK_START
            return "STEPPED_BACK"
        return "CANCELLED"

    def cancel(self):
        self.stage = self.PICK_START
        self.axis = self.DEFAULT_AXIS
        self.clear_numeric()
        return "CANCELLED"
