# -*- coding: utf-8 -*-
"""blender_labor.ops_io — 批量导入 / 批量导出
BatchImport：把一个文件夹（可含子文件夹）的模型批量导入并自动排开。
BatchExport：把所选物体逐个导出为独立文件（一物一文件）。
"""

import bpy
import os
from mathutils import Vector
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty

from . import core_utils as cu

IMPORT_EXTS = {'.obj', '.fbx', '.ply', '.stl', '.glb', '.gltf'}


def _import_file(path):
    """按扩展名调用 Blender 原生导入器（兼容 3.x / 4.x），返回新物体列表。"""
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    try:
        if ext == '.obj':
            if hasattr(bpy.ops.wm, 'obj_import'):
                bpy.ops.wm.obj_import(filepath=path)
            else:
                bpy.ops.import_scene.obj(filepath=path)
        elif ext == '.fbx':
            bpy.ops.import_scene.fbx(filepath=path)
        elif ext == '.ply':
            if hasattr(bpy.ops.wm, 'ply_import'):
                bpy.ops.wm.ply_import(filepath=path)
            else:
                bpy.ops.import_mesh.ply(filepath=path)
        elif ext == '.stl':
            if hasattr(bpy.ops.wm, 'stl_import'):
                bpy.ops.wm.stl_import(filepath=path)
            else:
                bpy.ops.import_mesh.stl(filepath=path)
        elif ext in ('.glb', '.gltf'):
            bpy.ops.import_scene.gltf(filepath=path)
        else:
            return []
    except Exception as ex:
        print("Labor 批量导入失败: %s (%s)" % (path, ex))
        return []
    return [o for o in bpy.data.objects if o not in before]


def _safe_name(name):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


# ---------------------------------------------------------------- 批量导入
class LABOR_OT_batch_import(bpy.types.Operator):
    """批量导入文件夹中的模型文件，逐个排开并各自放入集合"""
    bl_idname = "labor.batch_import"
    bl_label = "批量导入 (Batch Import)"
    bl_options = {'REGISTER', 'UNDO'}

    directory: StringProperty(name="文件夹", subtype='DIR_PATH')
    recursive: BoolProperty(name="包含子文件夹", default=False)
    gap: FloatProperty(name="模型间距", description="排开时模型包围盒之间的间距",
                       default=0.5, min=0.0, precision=4)
    to_collection: BoolProperty(name="按文件建集合", default=True)

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        root = bpy.path.abspath(self.directory)
        if not os.path.isdir(root):
            self.report({'WARNING'}, "文件夹无效")
            return {'CANCELLED'}
        files = []
        if self.recursive:
            for dirpath, _dirs, names in os.walk(root):
                for f in names:
                    if os.path.splitext(f)[1].lower() in IMPORT_EXTS:
                        files.append(os.path.join(dirpath, f))
        else:
            for f in sorted(os.listdir(root)):
                p = os.path.join(root, f)
                if os.path.isfile(p) and os.path.splitext(f)[1].lower() in IMPORT_EXTS:
                    files.append(p)
        if not files:
            self.report({'WARNING'}, "文件夹里没有可导入的模型（obj/fbx/ply/stl/glb/gltf）")
            return {'CANCELLED'}
        files.sort()
        cursor_x = 0.0
        ok = 0
        for path in files:
            new_objs = _import_file(path)
            tops = [o for o in new_objs if o.parent is None or o.parent not in new_objs]
            if not tops:
                continue
            ok += 1
            # 按文件建集合并移入
            if self.to_collection:
                stem = os.path.splitext(os.path.basename(path))[0]
                coll = bpy.data.collections.new(_safe_name(stem))
                context.scene.collection.children.link(coll)
                for o in tops:
                    for oc in list(o.users_collection):
                        oc.objects.unlink(o)
                    coll.objects.link(o)
            # 排开：底部落地、左侧接续
            mn, mx = cu.world_bbox(tops[0])
            for o in tops[1:]:
                om, ox = cu.world_bbox(o)
                mn = Vector((min(mn[i], om[i]) for i in range(3)))
                mx = Vector((max(mx[i], ox[i]) for i in range(3)))
            vec = Vector((cursor_x - mn.x, 0.0, -mn.z))
            for o in tops:
                cu.translate_world(o, vec)
            cursor_x += (mx - mn).x + self.gap
        self.report({'INFO'}, "成功导入 %d / %d 个文件" % (ok, len(files)))
        return {'FINISHED'}


# ---------------------------------------------------------------- 批量导出
class LABOR_OT_batch_export(bpy.types.Operator):
    """把每个所选顶层物体（连同子级）分别导出为独立文件"""
    bl_idname = "labor.batch_export"
    bl_label = "批量导出 (Batch Export)"
    bl_options = {'REGISTER'}

    directory: StringProperty(name="导出目录", subtype='DIR_PATH')
    fmt: EnumProperty(
        name="格式",
        items=(('FBX', "FBX", ""), ('OBJ', "OBJ", ""), ('GLTF', "glTF 2.0", ""),
               ('PLY', "PLY", ""), ('STL', "STL", "")),
        default='FBX',
    )
    apply_xform: BoolProperty(name="导出前应用变换", description="应用旋转与缩放（原点不动）",
                              default=True)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def _export_one(self, path):
        fmt = self.fmt
        if fmt == 'FBX':
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True)
        elif fmt == 'OBJ':
            if hasattr(bpy.ops.wm, 'obj_export'):
                bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
            else:
                bpy.ops.export_scene.obj(filepath=path, use_selection=True)
        elif fmt == 'GLTF':
            bpy.ops.export_scene.gltf(filepath=path, use_selection=True)
        elif fmt == 'PLY':
            if hasattr(bpy.ops.wm, 'ply_export'):
                bpy.ops.wm.ply_export(filepath=path, export_selected_objects=True)
            else:
                bpy.ops.export_mesh.ply(filepath=path, use_selection=True)
        elif fmt == 'STL':
            if hasattr(bpy.ops.wm, 'stl_export'):
                bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True)
            else:
                bpy.ops.export_mesh.stl(filepath=path, use_selection=True)

    def execute(self, context):
        out_dir = bpy.path.abspath(self.directory)
        if not out_dir:
            self.report({'WARNING'}, "请先选择导出目录")
            return {'CANCELLED'}
        os.makedirs(out_dir, exist_ok=True)
        ext = {'FBX': '.fbx', 'OBJ': '.obj', 'GLTF': '.glb', 'PLY': '.ply', 'STL': '.stl'}[self.fmt]
        tops = [o for o in context.selected_objects
                if o.parent is None or o.parent not in context.selected_objects]
        prev_selected = list(context.selected_objects)
        prev_active = context.view_layer.objects.active
        done = 0
        try:
            for ob in tops:
                group = [ob] + cu.children_recursive(ob)
                cu.select_only(context, group)
                if self.apply_xform:
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                path = os.path.join(out_dir, _safe_name(ob.name) + ext)
                self._export_one(path)
                done += 1
        finally:
            cu.select_only(context, prev_selected)
            if prev_active:
                context.view_layer.objects.active = prev_active
        self.report({'INFO'}, "导出了 %d 个文件到 %s" % (done, out_dir))
        return {'FINISHED'}


class LABOR_PT_io(bpy.types.Panel):
    bl_label = "批量导入 · 导出"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 7

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator(LABOR_OT_batch_import.bl_idname, icon='IMPORT')
        col.operator(LABOR_OT_batch_export.bl_idname, icon='EXPORT')


CLASSES = (LABOR_OT_batch_import, LABOR_OT_batch_export, LABOR_PT_io)
