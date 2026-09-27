"""OpenPali / material study — an original Blender scene.

Blender 5.2.2 / bpy 5.2.2. No external models, textures, or HDRIs.
Run: python scene.py --preview
     python scene.py
Or:  blender --background --python scene.py
Outputs are written beside this file. --preview writes only preview.png.
"""
from pathlib import Path
import math
import sys

import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent
PREVIEW = "--preview" in sys.argv
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
scene = bpy.context.scene


def linear(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb(hex_color):
    return tuple(linear(int(hex_color[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1,)


def material(name, color, roughness, transmission=0, metallic=0, ior=1.46):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgb(color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["IOR"].default_value = ior
    bsdf.inputs["Coat Weight"].default_value = 0.22
    bsdf.inputs["Coat Roughness"].default_value = 0.12
    return mat


porcelain = material("Porcelain / glazed chalk", "F4F6FF", 0.22)
cobalt = material("Cobalt acrylic / source #1557FF", "1557FF", 0.10, 0.78)
clear = material("Clear blue optical acrylic", "BED8FF", 0.055, 0.97)
paper = material("Matte gallery canvas", "F4F5F7", 0.82)


def block(name, loc, scale, mat, bevel=0.045):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    mod = obj.modifiers.new("Precision softened edges", "BEVEL")
    mod.width = bevel
    mod.segments = 6
    obj.modifiers.new("Weighted flat normals", "WEIGHTED_NORMAL")
    return obj


# Eleven cells trace an open ring. These are sculptural cells, not real parcels.
# The unoccupied corner makes the open-square silhouette recognizable.
cells = [(x, y) for x in range(4) for y in range(4)
         if (x in (0, 3) or y in (0, 3)) and (x, y) != (3, 0)]
assembly = bpy.data.objects.new("Open square / modular sculpture", None)
scene.collection.objects.link(assembly)
assembly.rotation_euler[2] = math.radians(-13)

for x, y in cells:
    center = (x - 1.5, y - 1.5)
    base = block(f"Porcelain cell {x}.{y}", (*center, 0.20), (0.94, 0.94, 0.34), porcelain)
    base.parent = assembly
    optic = block(f"Clear optical spacer {x}.{y}", (*center, 0.495), (0.88, 0.88, 0.18), clear, 0.025)
    optic.parent = assembly
    crown = block(f"Cobalt crown {x}.{y}", (*center, 0.84), (0.94, 0.94, 0.43), cobalt)
    crown.parent = assembly

# One offset tile is the deliberate invitation to complete the open shape.
tile = block("The next square / porcelain", (2.38, -1.56, 0.40), (0.94, 0.94, 0.34), porcelain)
tile.rotation_euler = (math.radians(6), math.radians(-10), math.radians(-13))
tile = block("The next square / optical blue", (2.30, -1.48, 1.02), (0.94, 0.94, 0.43), cobalt)
tile.rotation_euler = (math.radians(6), math.radians(-10), math.radians(-13))

floor = block("Gallery ground", (0, 0, -0.055), (200, 200, 0.1), paper, 0)


def point_at(obj, position):
    obj.rotation_euler = (Vector(position) - obj.location).to_track_quat("-Z", "Y").to_euler()


def area(name, loc, power, size, color, shape="DISK", size_y=None):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.shape = shape
    data.size = size
    if size_y:
        data.size_y = size_y
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = loc
    point_at(obj, (0, 0, 0.5))
    return obj


area("Large softbox / left key", (-4.5, -4, 9), 800, 5.5, (1, 0.97, 0.93))
area("Strip / right edge", (5, 2, 5), 950, 4.0, (0.8, 0.89, 1), "RECTANGLE", 1.3)
area("Top reflection card", (0, 3, 8), 420, 3, (1, 1, 1), "RECTANGLE", 6)
area("Front fill", (-2, -7, 3), 140, 5, (1, 1, 1))

scene.world = bpy.data.worlds.new("Neutral studio environment")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.82, 0.88, 1, 1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.18

cam_data = bpy.data.cameras.new("Orthographic studio lens")
cam = bpy.data.objects.new("Orthographic studio lens", cam_data)
scene.collection.objects.link(cam)
cam.location = (7.5, -10.5, 11.5)
point_at(cam, (0.15, 0, 0.5))
cam_data.type = "ORTHO"
cam_data.ortho_scale = 8.6
scene.camera = cam

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 32 if PREVIEW else 144
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 12
scene.cycles.transmission_bounces = 10
scene.cycles.transparent_max_bounces = 10
scene.render.resolution_x = 800 if PREVIEW else 1600
scene.render.resolution_y = 650 if PREVIEW else 1300
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0
scene.render.film_transparent = False

if PREVIEW:
    scene.render.filepath = str(OUT / "preview.png")
    bpy.ops.render.render(write_still=True)
else:
    # Save a complete editable scene before either render.
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "openpali-material.blend"))
    scene.render.filepath = str(OUT / "material-studio.png")
    bpy.ops.render.render(write_still=True)
    floor.hide_render = True
    scene.render.film_transparent = True
    scene.render.filepath = str(OUT / "material-transparent.png")
    bpy.ops.render.render(write_still=True)
    floor.hide_render = False
    scene.render.film_transparent = False
    scene.render.filepath = str(OUT / "material-studio.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "openpali-material.blend"))
