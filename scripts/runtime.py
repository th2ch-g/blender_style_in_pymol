"""Shared real-PyMOL harness for headless and Qt validation."""

from contextlib import nullcontext
from time import monotonic, sleep


class Viewer:
    def __init__(self, gui=False, width=1000, height=800):
        self.gui = gui
        self.application = None
        if gui:
            import pymol

            pymol.invocation.parse_args(["pymol", "-q", "-k"])
            pymol.invocation.options.show_splash = 0
            from pmg_qt.pymol_qt_gui import PyMOLApplication, PyMOLQtGUI

            self.application = PyMOLApplication(["blender-style-validation"])
            self.window = PyMOLQtGUI()
            self.widget = self.window.pymolwidget
            self.cmd = self.widget.cmd
            self.window.resize(width, height)
            self.window.show()
            self.pump(0.2)
        else:
            import pymol2

            self.instance = pymol2.PyMOL()
            self.instance.start()
            self.cmd = self.instance.cmd
        for setting in (
            "internal_gui",
            "internal_feedback",
            "internal_prompt",
            "seq_view",
            "movie_panel",
        ):
            self.cmd.set(setting, 0)

    def context(self):
        return self.widget if self.gui else nullcontext()

    def pump(self, seconds=0.02):
        if not self.gui:
            return
        end = monotonic() + seconds
        while monotonic() < end:
            self.application.processEvents()
            sleep(0.001)

    def draw(self):
        if not self.gui:
            return
        from OpenGL.GL import glFinish

        with self.widget:
            self.widget.paintGL()
            glFinish()

    def close(self):
        if self.gui:
            self.window.hide()
            self.application.processEvents()
        else:
            self.instance.stop()
