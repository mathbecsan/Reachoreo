"""Reachy Mini for the 3D rehearsal: Pollen's official rig, made light enough for a Quest 3 (two robots in view).

Run by Blender 5.1 in the background (see tools/build_reachy_glb.mjs, `npm run assets:reachy`):

    blender --background reachy_mini.blend --python build_reachy_glb.py -- --out reachy_mini_rehearse.glb

Source: github.com/pollen-robotics/reachy_mini_blender (Apache-2.0), 3D model and rig by Clément Plays.
What this changes (also logged in ASSETS.md):
  1. procedural materials -> flat colors (the same rule as the repo's export_gltf.py), then each part's color is
     baked into vertex colors, so one material per bone is enough (draw calls: ~400 -> ~6);
  2. parts are merged per bone they ride on: GLOBAL (base), Core (body), Core.001 (head), Antenna.L/R.002;
  3. decimated: head shell 632k -> 30k triangles, body 114k -> 8k, base 38k -> 6k (about 50k per robot);
  4. the two antenna rods are skinned in Blender (they can bend); here they ride rigidly on their antenna bone;
     the six Stewart-platform rods are left out: their IK doesn't survive glTF.
     The page draws six simple rods between the body and the head instead.
The armature is exported unchanged, so the page drives the same bones as RIG_MAPPING.md.
"""
import bpy
import bmesh
import sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "reachy_mini_rehearse.glb"
TARGET_TRIS = {"Core.001": 30000, "Core": 8000, "GLOBAL": 6000, "Antenna.L.002": 2000, "Antenna.R.002": 2000}   # per merged group; others are kept as they are
KEEP_BONES = ("GLOBAL", "Base", "Core", "Core.001", "Antenna.L.002", "Antenna.R.002")


def base_color(mat):
    """The flat color glTF will get: the principled base color, or the viewport color when it's procedural."""
    if mat is None:
        return (0.8, 0.8, 0.8, 1.0)
    if mat.use_nodes:
        for nd in mat.node_tree.nodes:
            if nd.type == "BSDF_PRINCIPLED":
                bc = nd.inputs["Base Color"]
                if bc.is_linked:
                    dc = mat.diffuse_color
                    return (dc[0], dc[1], dc[2], 1.0)
                v = bc.default_value
                return (v[0], v[1], v[2], 1.0)
    dc = mat.diffuse_color
    return (dc[0], dc[1], dc[2], 1.0)


def all_objs(c):
    o = list(c.objects)
    for ch in c.children:
        o += all_objs(ch)
    return o


def anchor_bone(o):
    """The bone a part rides on: its own bone parent, or its parent object's."""
    while o is not None:
        if o.parent_type == "BONE":
            return o.parent_bone
        o = o.parent
    return None


try:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
except RuntimeError:
    pass

arm = bpy.data.objects["Armature"]
parts = [o for o in all_objs(bpy.data.collections["MiniReachyRetopo"]) if o.type == "MESH"]
groups = {}
def dominant_bone(o):
    """A skinned part's main bone: the vertex group with the most weight (the antenna rods ride on Antenna.*)."""
    tot = {}
    for v in o.data.vertices:
        for g in v.groups:
            name = o.vertex_groups[g.group].name
            tot[name] = tot.get(name, 0.0) + g.weight
    return max(tot, key=tot.get) if tot else None


for o in parts:
    if any(m.type == "ARMATURE" for m in o.modifiers):
        b = dominant_bone(o)                                # the antenna rods are skinned (they bend in Blender);
        if b and b.startswith("Antenna"):                   # here they ride rigidly on their antenna bone
            groups.setdefault("Antenna.L.002" if ".L" in b else "Antenna.R.002", []).append(o)
        continue
    bone = anchor_bone(o)
    if bone is None or bone.startswith("Neck"):
        continue                                            # Stewart rods: drawn by the page instead
    if bone not in KEEP_BONES:
        bone = "Core.001" if "Head" in bone else "Core"
    groups.setdefault(bone, []).append(o)

shared = bpy.data.materials.new("Reachy")
shared.use_nodes = True
bsdf = next(n for n in shared.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
bsdf.inputs["Roughness"].default_value = 0.45
bsdf.inputs["Metallic"].default_value = 0.0
vc = shared.node_tree.nodes.new("ShaderNodeVertexColor")
vc.layer_name = "Col"
shared.node_tree.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])

dg = bpy.context.evaluated_depsgraph_get()
merged = []
for bone, objs in groups.items():
    bm = bmesh.new()
    col_layer = bm.loops.layers.color.new("Col")
    for o in objs:
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        me.transform(o.matrix_world)                        # into world space; re-parented to the bone below
        colors = [base_color(s.material) for s in o.material_slots] or [base_color(None)]
        tmp = bmesh.new()
        tmp.from_mesh(me)
        eo.to_mesh_clear()
        tl = tmp.loops.layers.color.new("Col")
        for f in tmp.faces:
            c = colors[min(f.material_index, len(colors) - 1)]
            for lp in f.loops:
                lp[tl] = c
        me2 = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me2)
        tmp.free()
        bm.from_mesh(me2)
        bpy.data.meshes.remove(me2)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(f"Reachy.{bone}")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(f"Reachy.{bone}", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.clear()
    mesh.materials.append(shared)
    for p in mesh.polygons:
        p.material_index = 0
    tris = len(mesh.polygons)
    if bone in TARGET_TRIS and tris > TARGET_TRIS[bone]:
        mod = obj.modifiers.new("decimate", "DECIMATE")
        mod.ratio = TARGET_TRIS[bone] / tris
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            bpy.ops.object.modifier_apply(modifier="decimate")
    # ride on the bone again, keeping the world placement
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_world = mw
    obj.data.color_attributes.active_color_name = "Col"
    merged.append(obj)
    print(f"group {bone}: {len(objs)} parts, {tris} -> {len(obj.data.polygons)} triangles")

for o in bpy.context.view_layer.objects:
    o.select_set(False)
for o in merged + [arm]:
    o.hide_set(False)
    o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(
    filepath=OUT, use_selection=True, export_format="GLB", export_apply=True, export_yup=True,
    export_texcoords=False, export_normals=True, export_vertex_color="ACTIVE", export_all_vertex_colors=False,
    export_draco_mesh_compression_enable=False, export_animations=False, export_skins=False, export_def_bones=False,
)
print(f"DONE -> {OUT}")
