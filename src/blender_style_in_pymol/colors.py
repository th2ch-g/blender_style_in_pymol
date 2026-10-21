"""Display-space colors applied only to the managed molecular copies."""

from colorsys import hsv_to_rgb

ELEMENTS = {
    "H": (1.0, 1.0, 1.0),
    "C": (0.486660, 0.486660, 0.486660),
    "N": (0.436627, 0.520322, 0.906332),
    "O": (0.906332, 0.437931, 0.436627),
    "P": (0.906332, 0.451437, 0.751749),
    "S": (0.906332, 0.866137, 0.252767),
    "F": (0.40, 0.83, 0.36),
    "Cl": (0.25, 0.78, 0.25),
    "Br": (0.65, 0.27, 0.18),
    "I": (0.56, 0.28, 0.76),
    "Fe": (0.82, 0.46, 0.25),
    "Zn": (0.55, 0.65, 0.75),
    "Mg": (0.42, 0.78, 0.53),
    "Ca": (0.42, 0.64, 0.80),
}
SECONDARY = {
    "H": (0.439216, 0.811765, 0.478431),
    "S": (1.000000, 0.423529, 0.423529),
    "L": (0.450980, 0.639216, 0.905882),
}
CHAINS = (
    (0.36, 0.65, 0.83),
    (0.93, 0.48, 0.52),
    (0.54, 0.76, 0.50),
    (0.90, 0.72, 0.35),
    (0.66, 0.54, 0.80),
    (0.32, 0.76, 0.72),
    (0.90, 0.58, 0.35),
    (0.72, 0.65, 0.58),
)


def define(cmd, name: str, rgb: tuple) -> int:
    cmd.set_color(name, rgb, quiet=1)
    return cmd.get_color_index(name)


def validate(cmd, value: str) -> str:
    if value in ("auto", "keep", "element", "chain", "secondary-structure", "rainbow"):
        return value
    if value.startswith("#") and len(value) == 7:
        try:
            int(value[1:], 16)
        except ValueError:
            pass
        else:
            return value
    if cmd.get_color_index(value) >= 0:
        return value
    raise ValueError("Unknown color; use a color theme, PyMOL color, or #rrggbb")


def apply(cmd, obj: str, options) -> None:
    theme = options.color
    if theme == "keep":
        return
    if theme == "auto":
        if options.material == "clay":
            theme = "#C89B7D"
        elif options.representation == "oxdna-ribbon":
            theme = "chain"
        elif options.representation.startswith("cartoon") or options.representation in (
            "ribbon",
            "preset-1",
            "preset-2",
            "preset-4",
        ):
            theme = "secondary-structure"
        else:
            theme = "element"
    if theme == "element":
        palette = {
            element: define(cmd, f"_bs_element_{element}", rgb)
            for element, rgb in ELEMENTS.items()
        }
        fallback = define(cmd, "_bs_element_other", (0.6, 0.6, 0.65))
        cmd.alter(obj, "color = palette.get(elem, fallback)", space=locals())
        if options.color == "auto" and options.representation in (
            "surface",
            "preset-3",
        ):
            cmd.color(palette["C"], f"{obj} and polymer.protein", quiet=1)
    elif theme == "secondary-structure":
        palette = {
            key: define(cmd, f"_bs_ss_{key}", rgb) for key, rgb in SECONDARY.items()
        }
        cmd.alter(obj, "color = palette.get(ss, palette['L'])", space=locals())
    elif theme == "chain":
        keys = set()
        cmd.iterate(obj, "keys.add((segi, chain))", space={"keys": keys})
        palette = {
            key: define(cmd, f"_bs_chain_{i % len(CHAINS)}", CHAINS[i % len(CHAINS)])
            for i, key in enumerate(sorted(keys))
        }
        cmd.alter(obj, "color = palette[(segi, chain)]", space={"palette": palette})
    elif theme == "rainbow":
        residues = {}
        cmd.iterate(
            obj,
            "residues.setdefault((segi, chain, resi), len(residues))",
            space=locals(),
        )
        colors = [
            define(cmd, f"_bs_rainbow_{i}", hsv_to_rgb((1 - i / 63) * 0.67, 0.64, 0.91))
            for i in range(64)
        ]
        palette = {
            key: colors[round(value / max(len(residues) - 1, 1) * 63)]
            for key, value in residues.items()
        }
        cmd.alter(obj, "color = palette[(segi, chain, resi)]", space=locals())
    else:
        if theme.startswith("#"):
            rgb = tuple(int(theme[i : i + 2], 16) / 255 for i in (1, 3, 5))
            theme = define(cmd, "_bs_hex_" + theme[1:].lower(), rgb)
        cmd.color(theme, obj, quiet=1)
