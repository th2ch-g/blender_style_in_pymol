"""Context-local indexed buffers and an isolated PyMOL drawing callback."""

from collections import OrderedDict
from ctypes import c_void_p
from dataclasses import dataclass, field
from weakref import ref

import numpy as np

from .lighting import FRAGMENT_SHADER, VERTEX_SHADER, parameters

_pools = {}


class Pool:
    def __init__(self, budget=128 * 1024**2):
        self.budget = budget
        self.buffers = OrderedDict()
        self.bytes = 0
        self.program = None

    def get(self, mesh):
        from OpenGL import GL as gl

        key = id(mesh)
        for old_key, (reference, handles, _, size) in list(self.buffers.items()):
            if reference() is None:
                gl.glDeleteBuffers(len(handles), handles)
                self.buffers.pop(old_key)
                self.bytes -= size
        if key in self.buffers:
            self.buffers.move_to_end(key)
            return self.buffers[key][1:3]
        data = np.column_stack(
            (mesh.vertices, mesh.normals, mesh.colors, mesh.occlusion)
        ).astype(np.float32)
        size = data.nbytes + mesh.faces.nbytes
        if size > self.budget:
            raise ValueError("Mesh GPU buffers exceed the cache budget; lower quality")
        while self.buffers and size + self.bytes > self.budget:
            _, (_, handles, _, old_size) = self.buffers.popitem(last=False)
            gl.glDeleteBuffers(len(handles), handles)
            self.bytes -= old_size
        handles = [int(gl.glGenBuffers(1)) for _ in range(2)]
        try:
            for target, handle, values in (
                (gl.GL_ARRAY_BUFFER, handles[0], data),
                (gl.GL_ELEMENT_ARRAY_BUFFER, handles[1], mesh.faces),
            ):
                gl.glBindBuffer(target, handle)
                gl.glBufferData(target, values.nbytes, values, gl.GL_STATIC_DRAW)
        except Exception:
            gl.glDeleteBuffers(len(handles), handles)
            raise
        self.buffers[key] = (ref(mesh), handles, mesh.faces.size, size)
        self.bytes += size
        return handles, mesh.faces.size

    def draw(self, drawing):
        from OpenGL import GL as gl
        from OpenGL.GL.shaders import compileProgram, compileShader

        program_before = int(gl.glGetIntegerv(gl.GL_CURRENT_PROGRAM))
        array_before = int(gl.glGetIntegerv(gl.GL_ARRAY_BUFFER_BINDING))
        element_before = int(gl.glGetIntegerv(gl.GL_ELEMENT_ARRAY_BUFFER_BINDING))
        client_before = int(gl.glGetIntegerv(gl.GL_CLIENT_ACTIVE_TEXTURE))
        gl.glPushAttrib(gl.GL_ALL_ATTRIB_BITS)
        gl.glPushClientAttrib(gl.GL_CLIENT_ALL_ATTRIB_BITS)
        try:
            if self.program is None:
                self.program = compileProgram(
                    compileShader(VERTEX_SHADER, gl.GL_VERTEX_SHADER),
                    compileShader(FRAGMENT_SHADER, gl.GL_FRAGMENT_SHADER),
                    validate=False,
                )
            gl.glUseProgram(self.program)

            def uniform(name, value, integer=False):
                location = gl.glGetUniformLocation(self.program, name)
                (gl.glUniform1i if integer else gl.glUniform1f)(location, value)

            from .presets import optical_parameters

            roughness, specular, unlit = parameters(drawing.material, drawing.params)
            uniform("roughness", roughness)
            uniform("specular", specular)
            uniform("unlit", unlit, True)
            uniform("opacity", 1 - drawing.transparency)
            uniform(
                "subsurface",
                optical_parameters(drawing.material, drawing.params)["subsurface"],
            )
            gl.glDisable(gl.GL_LIGHTING)
            gl.glDisable(gl.GL_FOG)
            gl.glDisable(gl.GL_CULL_FACE)
            gl.glEnable(gl.GL_DEPTH_TEST)
            gl.glDepthFunc(gl.GL_LEQUAL)
            gl.glDepthMask(drawing.transparency == 0)
            if drawing.transparency:
                gl.glEnable(gl.GL_BLEND)
                gl.glBlendFuncSeparate(
                    gl.GL_SRC_ALPHA,
                    gl.GL_ONE_MINUS_SRC_ALPHA,
                    gl.GL_ONE,
                    gl.GL_ONE_MINUS_SRC_ALPHA,
                )
            else:
                gl.glDisable(gl.GL_BLEND)
            for flag in (gl.GL_VERTEX_ARRAY, gl.GL_NORMAL_ARRAY, gl.GL_COLOR_ARRAY):
                gl.glEnableClientState(flag)
            gl.glClientActiveTexture(gl.GL_TEXTURE0)
            gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
            handles, count = self.get(drawing.mesh)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, handles[0])
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, handles[1])
            gl.glVertexPointer(3, gl.GL_FLOAT, 40, c_void_p(0))
            gl.glNormalPointer(gl.GL_FLOAT, 40, c_void_p(12))
            gl.glColorPointer(4, gl.GL_FLOAT, 40, c_void_p(24))
            indices = c_void_p(0)
            if drawing.transparency:
                modelview = np.asarray(gl.glGetDoublev(gl.GL_MODELVIEW_MATRIX)).T
                gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)
                direction = modelview[2, :3]
                key = direction.tobytes()
                if drawing.sort_key != key:
                    drawing.sorted_faces = drawing.mesh.faces[
                        np.argsort(drawing.centers @ direction)
                    ].copy()
                    drawing.sort_key = key
                indices = drawing.sorted_faces
            gl.glDrawElements(gl.GL_TRIANGLES, count, gl.GL_UNSIGNED_INT, indices)
        finally:
            gl.glPopClientAttrib()
            gl.glPopAttrib()
            gl.glUseProgram(program_before)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, array_before)
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, element_before)
            gl.glClientActiveTexture(client_before)


@dataclass
class Drawing:
    mesh: object
    material: str
    transparency: float
    params: dict = field(default_factory=dict)
    error: str = ""
    draws: int = 0

    def __post_init__(self):
        self.centers = self.mesh.vertices[self.mesh.faces].mean(axis=1)
        self.sort_key = None
        self.sorted_faces = None

    def get_extent(self):
        return [
            self.mesh.vertices.min(axis=0).tolist(),
            self.mesh.vertices.max(axis=0).tolist(),
        ]

    def __getstate__(self):
        return self.mesh, self.material, self.transparency, self.params

    def __setstate__(self, state):
        self.mesh, self.material, self.transparency = state[:3]
        self.params = state[3] if len(state) > 3 else {}
        self.error, self.draws = "", 0
        self.__post_init__()

    def __call__(self):
        if self.error:
            return
        try:
            from OpenGL import contextdata

            context = contextdata.getContext()
            pool = _pools.setdefault(context, Pool())
            pool.draw(self)
            self.draws += 1
        except Exception as exc:
            self.error = str(exc)
            print(
                f"blender_style: GPU shader failed: {exc}. Use backend=native or refresh after repairing the context."
            )
