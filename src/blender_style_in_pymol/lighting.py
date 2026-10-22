"""Linear-light GGX shading shared by the viewport and native ray export."""

import numpy as np

from .mesh import linear, srgb, unit

LIGHT_DIRECTIONS = unit([[-0.45, 0.55, 0.8], [0.5, 0.15, 0.6], [0.1, -0.5, 0.35]])
LIGHT_POWERS = np.array([0.2655, 0.1922, 0.4768])
LIGHT_RADII = np.array([0.304, 0.472, 0.404])


def parameters(material):
    roughness = {"glossy": 0.18, "matte": 0.85, "clay": 0.9, "transparent": 0.22}.get(
        material, 0.5
    )
    specular = 0 if material in ("matte", "clay") else 0.03374
    unlit = {"flat": 1, "ambient-occlusion": 2, "outline": 3}.get(material, 0)
    return roughness, specular, unlit


def shade(mesh, material, rotation):
    roughness, specular, unlit = parameters(material)
    color = linear(mesh.colors)
    ao = mesh.occlusion[:, None]
    if unlit in (1, 2):
        return srgb(color * ((1 - ao) ** 1.5 if unlit == 2 else 1)).clip(0, 1)
    normal = unit(mesh.normals @ np.asarray(rotation).reshape(3, 3))
    normal = np.where(normal[:, 2:] < 0, -normal, normal)
    if unlit == 3:
        cosine = np.clip(normal[:, 2:], 0, 1)
        transmitted = np.sqrt(np.maximum(1 - (1 - cosine**2) / 0.95**2, 0))
        rs = (
            (cosine - 0.95 * transmitted)
            / np.maximum(cosine + 0.95 * transmitted, 1e-8)
        ) ** 2
        rp = (
            (0.95 * cosine - transmitted)
            / np.maximum(0.95 * cosine + transmitted, 1e-8)
        ) ** 2
        fresnel = np.where(transmitted == 0, 1, (rs + rp) * 0.5)
        ramp = np.minimum((1 - ao) ** 1.5 / 0.30909145, 1) * 0.65065384
        return srgb(color * ramp * (1 - fresnel)).clip(0, 1)
    view = np.array([0, 0, 1])
    nv = np.maximum(normal[:, 2], 0.001)
    result = color * 0.35 * (1 - 0.5 * ao)
    for light, power, radius in zip(LIGHT_DIRECTIONS, LIGHT_POWERS, LIGHT_RADII):
        a2 = max(roughness, 0.08) ** 4 + (radius * 0.5) ** 2
        half = unit(light + view)
        cosine = normal @ light
        nl = np.where(
            np.abs(cosine) < radius,
            (cosine + radius) ** 2 / (4 * radius),
            np.maximum(cosine, 0),
        )
        nh = np.maximum(normal @ half, 0)
        vh = max(half[2], 0)
        fresnel = specular + (1 - specular) * (1 - vh) ** 5
        if specular == 0:
            fresnel = 0
        distribution = a2 / (np.pi * (nh * nh * (a2 - 1) + 1) ** 2)
        visibility = 0.5 / np.maximum(
            nl * np.sqrt(a2 + (1 - a2) * nv**2) + nv * np.sqrt(a2 + (1 - a2) * nl**2),
            1e-6,
        )
        result += (
            power
            * nl[:, None]
            * (color + (np.pi * fresnel * distribution * visibility)[:, None])
            * (1 - 0.18 * ao)
        )
    return srgb(result).clip(0, 1)


VERTEX_SHADER = """#version 120
varying vec3 normal;
varying vec4 color;
void main() {
    normal = normalize(gl_NormalMatrix * gl_Normal);
    color = gl_Color;
    vec4 p = gl_ModelViewProjectionMatrix * gl_Vertex;
    gl_Position = p;
    gl_ClipVertex = gl_ModelViewMatrix * gl_Vertex;
}
"""

FRAGMENT_SHADER = """#version 120
varying vec3 normal;
varying vec4 color;
uniform float roughness;
uniform float specular;
uniform float opacity;
uniform int unlit;
vec3 linearRGB(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 srgb(vec3 c) {
    return mix(12.92 * c, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}
vec3 illuminate(vec3 n, vec3 base, vec3 light, float power, float radius) {
    vec3 l = normalize(light);
    vec3 h = normalize(l + vec3(0.0, 0.0, 1.0));
    float nv = max(n.z, 0.001);
    float cosine = dot(n, l);
    float nl = abs(cosine) < radius ? pow(cosine + radius, 2.0) / (4.0 * radius) : max(cosine, 0.0);
    float nh = max(dot(n, h), 0.0);
    float a2 = pow(max(roughness, 0.08), 4.0) + pow(radius * 0.5, 2.0);
    float f = specular > 0.0 ? specular + (1.0 - specular) * pow(1.0 - max(h.z, 0.0), 5.0) : 0.0;
    float d = a2 / (3.14159265 * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
    float v = 0.5 / max(nl * sqrt(a2 + (1.0 - a2) * nv * nv) + nv * sqrt(a2 + (1.0 - a2) * nl * nl), 0.000001);
    return power * nl * (base + vec3(3.14159265 * f * d * v)) * (1.0 - 0.18 * color.a);
}
void main() {
    vec3 base = linearRGB(color.rgb);
    vec3 n = normalize(normal);
    if (n.z < 0.0) n = -n;
    vec3 result = base;
    if (unlit == 2) result *= pow(1.0 - color.a, 1.5);
    if (unlit == 3) {
        float c = clamp(n.z, 0.0, 1.0);
        float t = sqrt(max(1.0 - (1.0 - c*c) / (0.95*0.95), 0.0));
        float rs = pow((c - 0.95*t) / max(c + 0.95*t, 0.00000001), 2.0);
        float rp = pow((0.95*c - t) / max(0.95*c + t, 0.00000001), 2.0);
        float f = t == 0.0 ? 1.0 : 0.5 * (rs + rp);
        float ramp = min(pow(1.0 - color.a, 1.5) / 0.30909145, 1.0) * 0.65065384;
        result *= ramp * (1.0 - f);
    }
    if (unlit == 0) {
        result = base * 0.35 * (1.0 - 0.5 * color.a);
        result += illuminate(n, base, vec3(-0.45, 0.55, 0.8), 0.2655, 0.304);
        result += illuminate(n, base, vec3(0.5, 0.15, 0.6), 0.1922, 0.472);
        result += illuminate(n, base, vec3(0.1, -0.5, 0.35), 0.4768, 0.404);
    }
    gl_FragColor = vec4(clamp(srgb(result), 0.0, 1.0), opacity);
}
"""
