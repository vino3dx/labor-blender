# -*- coding: utf-8 -*-
"""blender_labor.ops_scatter — 散布
把所选物体随机散布到活动物体表面。
（Blender 的几何节点/粒子系统也能做散布但需要搭建节点；本工具提供"一键"轻量方案）
"""

import bpy
import random
from math import radians
from mathutils import Vector, Matrix
from bpy.props import IntProperty, FloatProperty, BoolProperty

from . import core_utils as cu


class LABOR_OT_scatter(bpy.types.Operator):
    """把除活动物体之外的所选物体随机散布到活动物体表面（关联复制，结果自动选中）"""
    bl_idname = "labor.scatter"
    bl_label = "散布 (Scatter)"
    bl_options = {'REGISTER', 'UNDO'}

    count: IntProperty(name="数量", description="散布实例总数", default=50, min=1)
    offset: FloatProperty(name="偏移", description="沿法线方向抬升", default=0.0, precision=4)
    align_normal: BoolProperty(name="法线对齐", description="贴合表面法线（适合坡面）",
                               default=True)
    random_rot_z: FloatProperty(name="随机旋转(°)", description="绕自身 Z 轴随机旋转的最大角度",
                                default=180.0, soft_min=0.0, soft_max=180.0)
    scale_min: FloatProperty(name="缩放最小", default=0.8, soft_min=0.01)
    scale_max: FloatProperty(name="缩放最大", default=1.2, soft_min=0.01)
    seed: IntProperty(name="随机种子", default=0)

    @classmethod
    def poll(cls, context):
        act = context.active_object
        return (act is not None and act.type == 'MESH'
                and len([o for o in context.selected_objects if o is not act]) >= 1)

    def execute(self, context):
        surface = context.active_object
        sources = [o for o in context.selected_objects if o is not surface]
        rng = random.Random(self.seed)
        results = []
        for _ in range(self.count):
            src = rng.choice(sources)
            pt, n = cu.random_surface_point(surface)
            if pt is None:
                continue
            dup = cu.linked_duplicate(context, src, src.name + "_scatter")
            up = n if self.align_normal else Vector((0, 0, 1))
            loc = pt + up * self.offset
            if self.align_normal:
                q = n.to_track_quat('Z', 'Y')
            else:
                q = src.matrix_world.to_quaternion()
            if self.random_rot_z > 0:
                q = q @ Matrix.Rotation(radians(rng.uniform(-self.random_rot_z,
                                                            self.random_rot_z)), 4, 'Z').to_quaternion()
            s = rng.uniform(self.scale_min, self.scale_max)
            dup.matrix_world = Matrix.LocRotScale(loc, q, Vector((s, s, s)))
            results.append(dup)
        if results:
            cu.select_only(context, results)
            self.report({'INFO'}, "散布了 %d 个实例" % len(results))
        else:
            self.report({'WARNING'}, "未能生成实例：请确认活动物体是网格")
        return {'FINISHED'}


class LABOR_PT_scatter(bpy.types.Panel):
    bl_label = "散布"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 1

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="选择散布物体，最后 Shift 选表面：", icon='SNAP_ON')
        col.operator(LABOR_OT_scatter.bl_idname, icon='PARTICLES')
        col.separator()
        col.label(text="提示：需要更复杂散布（密度贴图、\n风力过滤等）请用几何节点原生方案。",
                  icon='INFO')


CLASSES = (LABOR_OT_scatter, LABOR_PT_scatter)
