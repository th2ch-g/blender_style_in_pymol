"""Small deterministic structures, with no network access in the test suite."""

import math

import pymol2
import pytest
from chempy import Atom, Bond, models


def protein(residues=24):
    model = models.Indexed()
    for i in range(residues):
        angle = i * 1.7453
        center = (2.3 * math.cos(angle), 2.3 * math.sin(angle), 1.5 * i)
        for name, element, offset in (
            ("N", "N", (-0.7, 0, -0.4)),
            ("CA", "C", (0, 0, 0)),
            ("C", "C", (0.7, 0, 0.4)),
            ("O", "O", (0.9, 0.8, 0.5)),
        ):
            atom = Atom()
            atom.name, atom.symbol, atom.resn, atom.resi = (
                name,
                element,
                "ALA",
                str(i + 1),
            )
            atom.chain = "A" if i < residues // 2 else "B"
            atom.ss = "H" if i < residues // 2 else "S"
            atom.coord = [a + b for a, b in zip(center, offset)]
            atom.b = 10 + i
            model.add_atom(atom)
        base = 4 * i
        for a, b in ((base, base + 1), (base + 1, base + 2), (base + 2, base + 3)):
            bond = Bond()
            bond.index = [a, b]
            bond.order = 1
            model.add_bond(bond)
        if i and i != residues // 2:
            bond = Bond()
            bond.index = [base - 2, base]
            bond.order = 1
            model.add_bond(bond)
    return model


@pytest.fixture
def cmd():
    with pymol2.PyMOL() as instance:
        command = instance.cmd
        command.load_model(protein(), "sample")
        command.hide("everything", "sample")
        command.show("lines", "sample")
        command.color("orange", "sample")
        yield command
