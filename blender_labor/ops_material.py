# -*- coding: utf-8 -*-
"""blender_labor.ops_material — 按材质合并 / 复制 UV 通道 / 随机物体色
（Blender 原生已有：按 P 分离材质、材质槽管理、Ctrl+L 链接材质、Node Wrangler
   自动搭贴图节点——这些不重复。仅移植 Blender 缺失的三件）
"""

import bpy
import random
from mathutils import Color
from bpy.props import StringProperty, EnumProperty, FloatProperty

from . import core_utils as cu


# ---------------------------------------------------------------- 按材质合并
class LABOR_OT_join_by_material(bpy.types.Operator):
    """把使用相同材质的所选网格物体分别合并为一体（导入碎片化模型的救星）"""
    bl_idname = "labor.join_by_material"
    bl_label = "按材质合并 (Join by Material)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len([o for o in context.selected_objects if o.type == 'MESH']) >= 2

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        groups = {}
        for ob in meshes:
            mat = ob.material_slots[0].material if ob.material_slots else None
            key = mat.name if mat else "__无材质__"
            groups.setdefault(key, []).append(ob)
        joined = 0
        for key, grp in groups.items():
            if len(grp) < 2:
                continue
            for ob in grp[1:]:
                cu.make_single_user_data(ob)
            with context.temp_override(active_object=grp[0],
                                       selected_objects=grp,
                                       selected_editable_objects=grp):
                bpy.ops.object.join()
            joined += 1
        self.report({'INFO'}, "按材质合并为 %d 个物体（共 %d 种材质）" % (joined, len(groups)))
        return {'FINISHED'}


# ---------------------------------------------------------------- 复制 UV 通道
class LABOR_OT_copy_uv_layer(bpy.types.Operator):
    """把所选网格的一个 UV 通道复制为新的第二套 UV（一套原始 + 一套展平的常规做法）"""
    bl_idname = "labor.copy_uv_layer"
    bl_label = "复制 UV 通道"
    bl_options = {'REGISTER', 'UNDO'}

    source: StringProperty(name="源通道", description="要复制的 UV 通道名", default="UVMap")
    target: StringProperty(name="目标通道名", default="UV2")

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        done = skip = 0
        for ob in context.selected_objects:
            if ob.type != 'MESH':
                continue
            mesh = ob.data
            src = mesh.uv_layers.get(self.source)
            if src is None:
                skip += 1
                continue
            dst = mesh.uv_layers.get(self.target)
            if dst is None:
                dst = mesh.uv_layers.new(name=self.target)
            if dst is None:
                skip += 1
                continue
            if dst == src:
                skip += 1
                continue
            for poly in mesh.polygons:
                for li in poly.loop_indices:
                    dst.data[li].uv = src.data[li].uv
            done += 1
        self.report({'INFO'}, "复制了 %d 个物体的 UV（跳过 %d）" % (done, skip))
        return {'FINISHED'}


# ---------------------------------------------------------------- 随机物体色
class LABOR_OT_random_object_color(bpy.types.Operator):
    """给所选物体随机设置视口显示色（快速按颜色区分资产，等价 Max 的随机线框色）"""
    bl_idname = "labor.random_object_color"
    bl_label = "随机物体显示色"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="方式",
                       items=(('MULTIPLE', "多个", "每个物体一个随机颜色"),
                              ('SINGLE', "单个", "所选统一一个颜色")),
                       default='MULTIPLE')
    alpha: FloatProperty(name="不透明度", default=1.0, min=0.0, max=1.0)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        rng = random.Random()
        shared = Color((rng.random(), rng.random(), rng.random()))
        for ob in context.selected_objects:
            if self.mode == 'SINGLE':
                c = shared
            else:
                c = Color((rng.random(), rng.random(), rng.random()))
            ob.color = (c.r, c.g, c.b, self.alpha)
        return {'FINISHED'}


class LABOR_PT_material(bpy.types.Panel):
    bl_label = "材质 · UV"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 8

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator(LABOR_OT_join_by_material.bl_idname, icon='NODE_COMPOSITING')
        col.operator(LABOR_OT_copy_uv_layer.bl_idname, icon='UV')
        row = col.row(align=True)
        op = row.operator(LABOR_OT_random_object_color.bl_idname, text="随机色(多个)")
        op.mode = 'MULTIPLE'
        op = row.operator(LABOR_OT_random_object_color.bl_idname, text="统一色")
        op.mode = 'SINGLE'


CLASSES = (LABOR_OT_join_by_material, LABOR_OT_copy_uv_layer,
           LABOR_OT_random_object_color, LABOR_PT_material)
