"""Optional Qt controls, imported only when the user opens the plugin dialog."""


def show_dialog(cmd):
    from pymol.Qt import QtWidgets

    from . import blender_style
    from .presets import COLOR_THEMES, MATERIALS, REPRESENTATIONS

    application = QtWidgets.QApplication.instance()
    if application is None:
        raise RuntimeError("The style dialog requires the PyMOL Qt GUI")
    existing = getattr(cmd._pymol, "_blender_style_dialog", None)
    if existing is not None:
        existing.show()
        existing.raise_()
        existing.activateWindow()
        return existing

    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle("Blender / Molecular Nodes Style")
    dialog.resize(420, 360)
    layout = QtWidgets.QVBoxLayout(dialog)
    form = QtWidgets.QFormLayout()
    layout.addLayout(form)

    def combo(label, choices):
        widget = QtWidgets.QComboBox()
        widget.addItems(choices)
        form.addRow(label, widget)
        return widget

    selection = QtWidgets.QLineEdit("all")
    name = QtWidgets.QLineEdit("blender")
    form.addRow("Selection", selection)
    form.addRow("View name", name)
    representation = combo("Representation", REPRESENTATIONS)
    material = combo("Material", MATERIALS)
    color = combo("Color", COLOR_THEMES)
    color.setEditable(True)
    quality = combo("Quality", ("auto", "low", "medium", "high"))
    rendering = combo("Rendering", ("Automatic", "Smooth meshes", "Native PyMOL"))
    states = combo("States", ("All loaded states", "Current state"))
    transparency = QtWidgets.QDoubleSpinBox()
    transparency.setRange(0, 1)
    transparency.setSingleStep(0.1)
    form.addRow("Transparency", transparency)
    material.currentTextChanged.connect(
        lambda value: transparency.setValue(0.5 if value == "transparent" else 0)
    )
    keep = QtWidgets.QCheckBox("Keep existing scene lighting")
    layout.addWidget(keep)
    status = QtWidgets.QLabel("Smooth molecular shapes and soft studio materials.")
    status.setWordWrap(True)
    layout.addWidget(status)
    buttons = QtWidgets.QHBoxLayout()
    layout.addLayout(buttons)

    def report(action):
        try:
            result = action()
            if isinstance(result, dict):
                status.setText(
                    f"{result['atoms']:,} atoms · {result['states']} states · "
                    f"{result.get('backend', 'native')} · {result['seconds']:.3f} s"
                )
            else:
                status.setText("Done")
        except Exception as error:
            status.setText(str(error))

    def apply():
        return blender_style(
            material.currentText(),
            selection=selection.text(),
            representation=representation.currentText(),
            color=color.currentText(),
            quality=quality.currentText(),
            backend=("auto", "mesh", "native")[rendering.currentIndex()],
            name=name.text(),
            transparency=transparency.value(),
            lighting="keep" if keep.isChecked() else "auto",
            state="current" if states.currentIndex() else 0,
            _self=cmd,
        )

    def export():
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            dialog, "Save ray image", "figure.png", "PNG (*.png)"
        )
        if filename:
            return blender_style("ray", filename=filename, _self=cmd)

    for title, action in (
        ("Apply", apply),
        ("Reset view", lambda: blender_style("reset", name=name.text(), _self=cmd)),
        ("Save PNG", export),
    ):
        button = QtWidgets.QPushButton(title)
        button.clicked.connect(lambda checked=False, action=action: report(action))
        buttons.addWidget(button)
    cmd._pymol._blender_style_dialog = dialog
    dialog.show()
    return dialog
