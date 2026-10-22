"""Transactional native views with persistent selections and bounded preparation."""

from array import array
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter

from . import colors, geometry
from .presets import (
    DENSITY_REPRESENTATIONS,
    Options,
    estimate_bytes,
    lighting_settings,
    resolve_quality,
)

SESSION_KEY = "blender_style_in_pymol"


def _union(names):
    return " or ".join("%" + name for name in names) or "none"


def _value(cmd, key):
    kind, values = cmd.get_setting_tuple(key)
    return tuple(values) if kind == 4 else values[0]


def _same(left, right):
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(left - right) <= 1e-6
    return left == right


class Manager:
    def __init__(self, cmd):
        self.cmd = cmd

    @property
    def data(self):
        session = self.cmd._pymol.session
        if not hasattr(session, SESSION_KEY):
            setattr(
                session,
                SESSION_KEY,
                {
                    "version": 1,
                    "entries": {},
                    "originals": [],
                    "lighting": {"base": {}, "applied": {}},
                },
            )
        return getattr(session, SESSION_KEY)

    @property
    def entries(self):
        return self.data["entries"]

    def _delete(self, names):
        existing = set(self.cmd.get_names("all"))
        for name in names:
            getattr(self.cmd._pymol.session, "blender_style_meshes", {}).pop(name, None)
            getattr(self.cmd._pymol.session, "blender_style_callbacks", {}).pop(
                name, None
            )
            getattr(self.cmd._pymol, "_blender_drawings", {}).pop(name, None)
            if name in existing:
                self.cmd.delete(name)

    def _remember(self, selection):
        cmd = self.cmd
        originals = self.data["originals"]
        uncovered = (
            f"(%{selection}) and not ({_union(x['selection'] for x in originals)})"
        )
        rows = defaultdict(lambda: array("i"))
        cmd.iterate(
            uncovered, "rows[(model, reps)].append(index)", space={"rows": rows}
        )
        added = []
        try:
            for (obj, mask), indices in rows.items():
                name = cmd.get_unused_name("_bs_original")
                cmd.select_list(name, obj, list(indices), mode="index", quiet=1)
                cmd.disable(name)
                added.append({"selection": name, "mask": mask})
        except Exception:
            self._delete(x["selection"] for x in added)
            raise
        originals.extend(added)

    def _restore_sources(self):
        cmd = self.cmd
        names = set(cmd.get_names("all"))
        covered = _union(entry["source_selection"] for entry in self.entries.values())
        retained = []
        for original in self.data["originals"]:
            name = original["selection"]
            if name not in names:
                continue
            released = f"%{name} and not ({covered})"
            if cmd.count_atoms(released):
                cmd.alter(released, "reps = mask", space={"mask": original["mask"]})
                cmd.rebuild(released)
            cmd.select(name, f"%{name} and ({covered})", enable=0, quiet=1)
            if cmd.count_atoms(name):
                retained.append(original)
            else:
                cmd.delete(name)
        self.data["originals"] = retained
        if self.entries:
            cmd.hide("everything", covered)

    def _scene(self, force=False):
        cmd = self.cmd
        state = self.data["lighting"]
        desired = {}
        for entry in self.entries.values():
            options = entry["options"]
            if options["lighting"] != "keep":
                material = (
                    options["material"]
                    if options["lighting"] == "auto"
                    else options["lighting"]
                )
                desired = lighting_settings(material)
        if any(entry["states"] > 1 for entry in self.entries.values()):
            desired["defer_builds_mode"] = 3
        for entry in self.entries.values():
            if entry["options"]["representation"] == "oxdna-ribbon":
                desired["cgo_sphere_quality"] = {"low": 1, "medium": 2, "high": 3}[
                    entry["quality"]
                ]
                desired["cgo_ellipsoid_quality"] = desired["cgo_sphere_quality"]
        for key in set(state["applied"]) | set(desired):
            current = _value(cmd, key)
            owned = key in state["applied"]
            changed = owned and not _same(current, state["applied"][key])
            if key not in desired:
                if owned and not changed:
                    cmd.set(key, state["base"][key], quiet=1)
                state["base"].pop(key, None)
                state["applied"].pop(key, None)

            elif force or (owned and not changed):
                if not owned or changed:
                    state["base"][key] = current
                cmd.set(key, desired[key], quiet=1)
                state["applied"][key] = _value(cmd, key)
            elif changed:
                state["base"].pop(key, None)
                state["applied"].pop(key, None)

    def _scene_snapshot(self):
        return {
            key: _value(self.cmd, key)
            for key in (
                *lighting_settings("studio"),
                "defer_builds_mode",
                "cgo_sphere_quality",
                "cgo_ellipsoid_quality",
            )
        }

    def _restore_scene(self, values):
        for key, value in values.items():
            self.cmd.set(key, value, quiet=1)

    def maintenance(self):
        names = set(self.cmd.get_names("all"))
        markers = [entry["source_selection"] for entry in self.entries.values()] + [
            item["selection"] for item in self.data["originals"]
        ]
        if markers and not names.intersection(markers):
            self._delete(
                obj for entry in self.entries.values() for obj in entry["objects"]
            )
            self.data["entries"].clear()
            self.data["originals"].clear()
            self.data["lighting"] = {"base": {}, "applied": {}}
            return
        stale = [
            name
            for name, entry in self.entries.items()
            if name not in names
            or entry["source_selection"] not in names
            or any(obj not in names for obj in entry["objects"])
            or any(obj not in names for obj in entry.get("maps", ()))
        ]
        for name in stale:
            self.reset(name, maintenance=False)

    def _source(self, selection):
        cmd = self.cmd
        generated = [
            obj
            for entry in self.entries.values()
            for obj in entry["objects"]
            if cmd.get_type(obj) == "object:molecule"
        ]
        expression = f"({selection}) and not ({_union(generated)})"
        objects = [
            obj
            for obj in (cmd.get_object_list(expression) or [])
            if cmd.get_type(obj) == "object:molecule"
        ]
        if not objects:
            raise ValueError("selection contains no source molecular atoms")
        name = cmd.get_unused_name("_bs_source")
        cmd.select(name, f"({expression}) and ({_union(objects)})", enable=0, quiet=1)
        if not cmd.count_atoms(name):
            cmd.delete(name)
            raise ValueError("selection contains no source molecular atoms")
        return name, objects

    def apply(self, options: Options, refresh=False):
        self.maintenance()
        if options.representation in DENSITY_REPRESENTATIONS:
            from .presets import needs_cycles

            if needs_cycles(options):
                raise ValueError(
                    "Cycles materials require a molecular mesh representation"
                )
            from .density import apply

            return apply(self, options)
        cmd = self.cmd
        started = perf_counter()
        colors.validate(cmd, options.color)
        if options.name in cmd.get_names("all") and options.name not in self.entries:
            raise ValueError(
                f"name '{options.name}' already belongs to another object or selection"
            )
        source, source_objects = self._source(options.selection)
        created = []
        previous = None
        scene = None
        try:
            rows = []
            for original in source_objects:
                selected = f"%{source} and %{original}"
                atoms = cmd.count_atoms(selected)
                states = cmd.count_states(original)
                if options.state > states:
                    raise ValueError(
                        f"state {options.state} is absent from {original} ({states} states)"
                    )
                states = states if options.state == 0 else 1
                rows.append((original, selected, atoms, states))
            atoms = sum(row[2] for row in rows)
            states = max(row[3] for row in rows)
            coordinate_bytes = sum(row[2] * row[3] * 12 for row in rows)
            quality = resolve_quality(options.quality, atoms, states)
            backbone = cmd.count_atoms(
                f"%{source} and ((polymer.protein and name CA) or (polymer.nucleic and name C4'))"
            )
            use_mesh = geometry.mesh_backend(options, atoms, states, quality, backbone)
            estimate = estimate_bytes(
                options.representation, quality, atoms, backbone, coordinate_bytes
            )
            if options.representation == "oxdna-ribbon":
                estimate += atoms * states * 2048
            if use_mesh:
                estimate = (
                    coordinate_bytes
                    + atoms * 384
                    + states
                    * geometry.mesh_estimate(
                        options.representation, quality, atoms, backbone
                    )
                )
            old = self.entries.get(options.name)
            resident = sum(entry["estimated_bytes"] for entry in self.entries.values())
            if (
                old
                and not refresh
                and self._can_update(old, options, source, quality, use_mesh)
            ):
                if (
                    old["quality"] != quality
                    and resident + estimate > options.memory_mb * 1024**2
                ):
                    raise ValueError(
                        "Quality change exceeds memory_mb; use a smaller selection or increase the budget"
                    )
                return self._update(old, options, quality, estimate, started)
            if resident + estimate > options.memory_mb * 1024**2:
                raise ValueError(
                    f"Estimated preparation memory {(resident + estimate) / 1024**2:.1f} MiB exceeds "
                    f"memory_mb={options.memory_mb:g}. Use state=1, a smaller selection, reset unused views, "
                    "or explicitly increase memory_mb."
                )
            enabled = set(cmd.get_names("objects", enabled_only=1))
            mappings = []
            prepared_bytes = 0
            for original, selected, count, frame_count in rows:
                obj = cmd.get_unused_name("_bs_view")
                created.append(obj)
                cmd.create(
                    obj,
                    selected,
                    source_state=options.state,
                    target_state=0 if options.state == 0 else 1,
                    zoom=0,
                    quiet=1,
                )
                cmd.disable(obj)
                colors.apply(cmd, obj, options)
                extras = geometry.prepare(
                    cmd,
                    obj,
                    options,
                    quality,
                    use_mesh,
                    options.memory_mb * 1024**2 - resident - prepared_bytes,
                )
                created.extend(extras)
                prepared_bytes += count * (384 + frame_count * 12)
                mesh_cache = getattr(cmd._pymol.session, "blender_style_meshes", {})
                prepared_bytes += sum(
                    mesh.nbytes * 2 + len(mesh.faces) * 180
                    for extra in extras
                    for mesh in mesh_cache.get(extra, ())
                )
                mappings.append(
                    {"object": obj, "source": original, "enabled": original in enabled}
                )
                mappings.extend(
                    {
                        "object": extra,
                        "source": original,
                        "enabled": original in enabled,
                    }
                    for extra in extras
                )
            entry = {
                "options": asdict(options),
                "objects": list(created),
                "source_selection": source,
                "mapping": mappings,
                "atoms": atoms,
                "states": states,
                "quality": quality,
                "backend": "mesh"
                if any(
                    obj in getattr(cmd._pymol.session, "blender_style_meshes", {})
                    for obj in created
                )
                else "native",
                "coordinate_bytes": coordinate_bytes,
                "estimated_bytes": estimate,
                "seconds": perf_counter() - started,
            }
            previous = deepcopy(self.data)
            scene = self._scene_snapshot()
            self._remember(source)
            cmd.group(options.name, " ".join(created), quiet=1)
            cmd.group(options.name, action="close", quiet=1)
            self.entries.pop(options.name, None)
            self.entries[options.name] = entry
            self._scene(force=True)
            for mapping in mappings:
                if mapping["enabled"]:
                    cmd.enable(mapping["object"])
            self._restore_sources()
            if old:
                self._delete([*old["objects"], old["source_selection"]])
            entry["seconds"] = perf_counter() - started
            return dict(entry)
        except Exception:
            if previous is not None:
                originals = {x["selection"] for x in previous["originals"]}
                for item in self.data["originals"]:
                    if item["selection"] not in originals:
                        cmd.alter(
                            item["selection"],
                            "reps = mask",
                            space={"mask": item["mask"]},
                        )
                        self._delete([item["selection"]])
                self.data.clear()
                self.data.update(previous)
                if options.name not in previous["entries"]:
                    self._delete([options.name])
                self._restore_scene(scene)
            self._delete(created)
            self._delete([source])
            self._restore_sources()
            raise
        finally:
            if not any(
                entry["source_selection"] == source for entry in self.entries.values()
            ):
                self._delete([source])

    def _can_update(self, entry, options, selection, quality, use_mesh):
        from .presets import OPTICAL_PARAMETERS

        if entry.get("kind") == "density" or options.representation == "oxdna-ribbon":
            return False
        before = entry["options"]
        if (entry.get("backend", "native") == "mesh") != use_mesh:
            return False
        if use_mesh and (before["lighting"] == "auto") != (options.lighting == "auto"):
            return False
        if use_mesh and (
            entry["quality"] != quality
            or any(
                obj not in getattr(self.cmd._pymol.session, "blender_style_meshes", {})
                for obj in entry["objects"]
                if self.cmd.get_type(obj) == "object:cgo"
            )
        ):
            return False
        if options.color == "auto" and (options.material == "clay") != (
            before["material"] == "clay"
        ):
            return False
        for key in ("representation", "color", "state"):
            if before[key] != getattr(options, key):
                return False
        if {
            k: v for k, v in before["params"].items() if k not in OPTICAL_PARAMETERS
        } != {k: v for k, v in options.params.items() if k not in OPTICAL_PARAMETERS}:
            return False
        old = entry["source_selection"]
        return not self.cmd.count_atoms(
            f"(%{old} and not %{selection}) or (%{selection} and not %{old})"
        )

    def _update(self, entry, options, quality, estimate, started):
        from .presets import geometry_settings, material_settings

        cmd = self.cmd
        updates = material_settings(options.material, quality, options.transparency)
        if quality != entry["quality"]:
            updates.update(
                geometry_settings(options.representation, quality, options.params)
            )
        saved = {
            (obj, key): cmd.get(key, obj) for obj in entry["objects"] for key in updates
        }
        previous = deepcopy(self.data)
        scene = self._scene_snapshot()
        try:
            for obj in entry["objects"]:
                meshes = getattr(cmd._pymol.session, "blender_style_meshes", {}).get(
                    obj
                )
                if meshes:
                    from .mesh import load

                    load(cmd, obj, meshes, options)
                for key, value in updates.items():
                    cmd.set(key, value, obj, quiet=1)
            self.entries.pop(options.name)
            entry.update(
                options=asdict(options),
                quality=quality,
                estimated_bytes=estimate,
                seconds=perf_counter() - started,
            )
            self.entries[options.name] = entry
            self._scene(force=True)
        except Exception:
            for obj in entry["objects"]:
                meshes = getattr(cmd._pymol.session, "blender_style_meshes", {}).get(
                    obj
                )
                if meshes:
                    from .mesh import load

                    load(
                        cmd,
                        obj,
                        meshes,
                        Options(**previous["entries"][options.name]["options"]),
                    )
            for (obj, key), value in saved.items():
                cmd.set(key, value, obj, quiet=1)
            self.data.clear()
            self.data.update(previous)
            self._restore_scene(scene)
            raise
        return dict(entry)

    def reset(self, name="all", maintenance=True):
        if maintenance:
            self.maintenance()
        selected = list(self.entries) if name == "all" else [name]
        removed = 0
        for key in selected:
            entry = self.entries.pop(key, None)
            if entry:
                self._delete([*entry["objects"], key, entry["source_selection"]])
                removed += 1
        self._restore_sources()
        self._scene()
        return removed

    def refresh(self, name="all"):
        self.maintenance()
        keys = list(self.entries) if name == "all" else [name]
        if any(key not in self.entries for key in keys):
            raise ValueError(f"Unknown managed view: {name}")
        results = []
        for key in keys:
            results.append(
                self.apply(Options(**self.entries[key]["options"]), refresh=True)
            )
        return results

    def select_source(self, selection, target="sele"):
        cmd = self.cmd
        matches = defaultdict(set)
        picked = defaultdict(set)
        cmd.iterate(selection, "picked[model].add(rank)", space={"picked": picked})
        for entry in self.entries.values():
            for mapping in entry["mapping"]:
                ranks = picked.get(mapping["object"])
                if ranks:
                    cmd.iterate(
                        f"%{entry['source_selection']} and %{mapping['source']}",
                        "matches[model].add(index) if rank in ranks else None",
                        space={"matches": matches, "ranks": ranks},
                    )
        if not matches:
            raise ValueError("selection contains no atoms from a managed view")
        parts = []
        try:
            for obj, indices in matches.items():
                part = cmd.get_unused_name("_bs_pick")
                parts.append(part)
                cmd.select_list(part, obj, sorted(indices), mode="index", quiet=1)
            return cmd.select(target, _union(parts), quiet=1)
        finally:
            self._delete(parts)


def manager_for(cmd):
    owner = cmd._pymol
    manager = getattr(owner, "_blender_style_manager", None)
    if manager is None:
        manager = Manager(cmd)
        owner._blender_style_manager = manager
    return manager
