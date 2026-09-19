# -*- coding: utf-8 -*-
"""blender_labor.ops_array — 多物体线性阵列
（单物体的线性阵列 Blender 原生"阵列修改器"已覆盖，不重复；
   本工具用于把【多个不同物体】沿 X/Y/Z 轴批量复制排列，如栏杆柱、货架、座椅排）
"""

import bpy
from mathutils import Matrix, Vector
from bpy.props import IntProperty, FloatVectorProperty, BoolProperty

from . import core_utils as cu


class LABOR_OT_array(bpy.types.Operator):
    """把所选物体沿各轴复制排列（偏移量为物体局部轴向）"""
    bl_idname = "labor.array"
    bl_label = "多物体阵列 (Array)"
    bl_options = {'REGISTER', 'UNDO'}

    count_x: IntProperty(name="X 数量", default=1, min=1)
    count_y: IntProperty(name="Y 数量", default=1, min=1)
    count_z: IntProperty(name="Z 数量", default=1, min=1)
    offset: FloatVectorProperty(name="步距", size=3, default=(2.0, 2.0, 2.0), precision=4,
                               description="每一步在 X/Y/Z 上的距离（物体局部轴向）")
    linked_data: BoolProperty(name="关联数据", description="副本共享网格数据（省内存）",
                              default=True)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def _duplicate(self, context, base):
        if self.linked_data:
            return cu.linked_duplicate(context, base)
        new = base.copy()
        if base.data:
            new.data = base.data.copy()
        context.collection.objects.link(new)
        return new

    def execute(self, context):
        bases = [o for o in context.selected_objects]
        results = []
        cx, cy, cz = self.count_x, self.count_y, self.count_z
        for base in bases:
            for ix in range(cx):
                for iy in range(cy):
                    for iz in range(cz):
                        if ix == 0 and iy == 0 and iz == 0:
                            continue
                        dup = self._duplicate(context, base)
                        shift = Vector((ix * self.offset.x, iy * self.offset.y,
                                        iz * self.offset.z))
                        dup.matrix_world = base.matrix_world @ Matrix.Translation(shift)
                        results.append(dup)
        if results:
            cu.select_only(context, results)
            self.report({'INFO'}, "阵列生成了 %d 个副本" % len(results))
        return {'FINISHED'}


class LABOR_PT_array(bpy.types.Panel):
    bl_label = "多物体阵列"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 4

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="多个不同物体批量排列：", icon='MOD_ARRAY')
        col.operator(LABOR_OT_array.bl_idname, icon='DUPLICATE')
        col.label(text="单物体阵列请直接用原生\"阵列修改器\"。", icon='INFO')


CLASSES = (LABOR_OT_array, LABOR_PT_array)
