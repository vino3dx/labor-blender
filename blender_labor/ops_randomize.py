# -*- coding: utf-8 -*-
"""blender_labor.ops_randomize — 随机化 / 重置变换 / 替换器
（对应 AssemblyTool 的 Randomizer 与 Replacer）
"""

import bpy
import random
from math import radians
from mathutils import Vector, Euler
from bpy.props import (BoolProperty, IntProperty, FloatProperty, FloatVectorProperty,
                       PointerProperty)

from . import core_utils as cu


# ---------------------------------------------------------------- 随机化
class LABOR_OT_randomize(bpy.types.Operator):
    """对所选物体做可控随机扰动（位置/旋转/缩放，Ctrl+Z 可撤销，换种子重掷）"""
    bl_idname = "labor.randomize"
    bl_label = "随机化变换 (Randomize)"
    bl_options = {'REGISTER', 'UNDO'}

    use_loc: BoolProperty(name="随机位置", default=True)
    loc_min: FloatVectorProperty(name="位置范围Min", size=3, default=(-0.2, -0.2, 0.0),
                                 precision=4)
    loc_max: FloatVectorProperty(name="位置范围Max", size=3, default=(0.2, 0.2, 0.0),
                                 precision=4)
    use_rot: BoolProperty(name="随机旋转", default=True)
    rot_min: FloatVectorProperty(name="旋转范围Min(°)", size=3, default=(-10, -10, -180))
    rot_max: FloatVectorProperty(name="旋转范围Max(°)", size=3, default=(10, 10, 180))
    use_scale: BoolProperty(name="随机缩放", default=True)
    uniform_scale: BoolProperty(name="等比缩放", default=True)
    scale_min: FloatProperty(name="缩放最小", default=0.9, soft_min=0.01)
    scale_max: FloatProperty(name="缩放最大", default=1.1, soft_min=0.01)
    seed: IntProperty(name="随机种子", default=0)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        rng = random.Random(self.seed)
        n = 0
        for ob in context.selected_objects:
            if self.use_loc:
                d = Vector((rng.uniform(self.loc_min[i], self.loc_max[i]) for i in range(3)))
                if d.length > 0:
                    cu.translate_world(ob, d)
            if self.use_rot:
                e = Euler((radians(rng.uniform(self.rot_min[i], self.rot_max[i]))
                           for i in range(3)), 'XYZ')
                if ob.rotation_mode == 'QUATERNION':
                    ob.rotation_quaternion = (ob.rotation_quaternion @ e.to_quaternion())
                else:
                    ob.rotation_euler.rotate(e)
            if self.use_scale:
                if self.uniform_scale:
                    s = rng.uniform(self.scale_min, self.scale_max)
                    ob.scale = ob.scale * Vector((s, s, s))
                else:
                    ob.scale = ob.scale * Vector((rng.uniform(self.scale_min, self.scale_max)
                                                  for _ in range(3)))
            n += 1
        self.report({'INFO'}, "已随机化 %d 个物体" % n)
        return {'FINISHED'}


# ---------------------------------------------------------------- 重置（归零）
class LABOR_OT_clear_rotation(bpy.types.Operator):
    """把所选物体旋转归零（对齐世界坐标轴）"""
    bl_idname = "labor.clear_rotation"
    bl_label = "旋转归零"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            if ob.rotation_mode == 'QUATERNION':
                ob.rotation_quaternion.identity()
            else:
                ob.rotation_euler = (0.0, 0.0, 0.0)
        return {'FINISHED'}


class LABOR_OT_clear_scale(bpy.types.Operator):
    """把所选物体缩放恢复为 1（物体自身坐标下）"""
    bl_idname = "labor.clear_scale"
    bl_label = "缩放至 100%"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            ob.scale = (1.0, 1.0, 1.0)
        return {'FINISHED'}


# ---------------------------------------------------------------- 替换器
class LABOR_OT_replace_with_active(bpy.types.Operator):
    """把所选物体（除活动物体外）替换为活动物体的关联副本，并继承其变换"""
    bl_idname = "labor.replace_with_active"
    bl_label = "替换为活动物体"
    bl_options = {'REGISTER', 'UNDO'}

    keep_scale: BoolProperty(name="保留原缩放", description="替换体沿用被替换物体的缩放",
                             default=False)

    @classmethod
    def poll(cls, context):
        act = context.active_object
        return act is not None and len([o for o in context.selected_objects
                                        if o is not act]) >= 1

    def execute(self, context):
        act = context.active_object
        targets = [o for o in context.selected_objects if o is not act]
        results = []
        for ob in targets:
            dup = cu.linked_duplicate(context, act, ob.name)
            dup.matrix_world = ob.matrix_world.copy()
            if self.keep_scale:
                dup.scale = ob.scale.copy()
            results.append(dup)
        cu.delete_objects(context, targets)
        cu.select_only(context, results)
        self.report({'INFO'}, "替换了 %d 个物体" % len(results))
        return {'FINISHED'}


class LABOR_OT_replace_random_from_collection(bpy.types.Operator):
    """把所选物体逐个替换为指定集合内物体的随机关联副本（换树/换人群防整齐划一）"""
    bl_idname = "labor.replace_random_from_collection"
    bl_label = "从集合随机替换"
    bl_options = {'REGISTER', 'UNDO'}

    collection: PointerProperty(name="替换来源集合", type=bpy.types.Collection)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        if not self.collection:
            self.report({'WARNING'}, "请先指定替换来源集合")
            return {'CANCELLED'}
        pool = [o for o in self.collection.all_objects if o.type in {'MESH', 'CURVE'}]
        if not pool:
            self.report({'WARNING'}, "来源集合里没有可用的网格物体")
            return {'CANCELLED'}
        rng = random.Random()
        targets = list(context.selected_objects)
        results = []
        for ob in targets:
            src = rng.choice(pool)
            dup = cu.linked_duplicate(context, src, ob.name)
            dup.matrix_world = ob.matrix_world.copy()
            results.append(dup)
        cu.delete_objects(context, targets)
        cu.select_only(context, results)
        self.report({'INFO'}, "随机替换了 %d 个物体" % len(results))
        return {'FINISHED'}


class LABOR_PT_organize(bpy.types.Panel):
    bl_label = "随机化 · 替换"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 3

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="随机化：", icon='MOD_NOISE')
        col.operator(LABOR_OT_randomize.bl_idname, icon='FILE_REFRESH')
        row = col.row(align=True)
        row.operator(LABOR_OT_clear_rotation.bl_idname, text="旋转归零")
        row.operator(LABOR_OT_clear_scale.bl_idname, text="缩放100%")
        col.separator()
        col.label(text="替换器：", icon='MOD_MESHDEFORM')
        col.operator(LABOR_OT_replace_with_active.bl_idname)
        col.operator(LABOR_OT_replace_random_from_collection.bl_idname)


CLASSES = (LABOR_OT_randomize, LABOR_OT_clear_rotation, LABOR_OT_clear_scale,
           LABOR_OT_replace_with_active, LABOR_OT_replace_random_from_collection,
           LABOR_PT_organize)
