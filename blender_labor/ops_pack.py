# -*- coding: utf-8 -*-
"""blender_labor.ops_pack — 网格排布 / 网格打包
GridPacker：把所选物体整齐排进网格（资产清点、展示图）。
ShelfPacker：把所选物体按占地面积紧密堆积（3D 打印排版、摆盘出图）。
"""

import bpy
import math
import random
from mathutils import Vector
from bpy.props import IntProperty, FloatProperty, EnumProperty, BoolProperty

from . import core_utils as cu


# ---------------------------------------------------------------- 网格排布
class LABOR_OT_grid_pack(bpy.types.Operator):
    """把所选物体整齐排布成网格（底部落地）"""
    bl_idname = "labor.grid_pack"
    bl_label = "网格排布 (Grid Pack)"
    bl_options = {'REGISTER', 'UNDO'}

    columns: IntProperty(name="列数", description="0 = 自动（开平方）", default=0, min=0)
    spacing: FloatProperty(name="间距", default=0.5, min=0.0, precision=4)
    sort: EnumProperty(
        name="排序",
        items=(('SIZE_DESC', "按尺寸递减", "大件在前"),
               ('SIZE_ASC', "按尺寸递增", "小件在前"),
               ('NONE', "不排序", "保持当前顺序")),
        default='SIZE_DESC',
    )
    ground: BoolProperty(name="底部落地", description="排布后底部贴地 (Z=0)", default=True)

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        objs = [o for o in context.selected_objects]
        items = [(cu.world_bbox(o), o) for o in objs]
        if self.sort != 'NONE':
            items.sort(key=lambda it: -(it[0][1] - it[0][0]).length
                       if self.sort == 'SIZE_DESC' else (it[0][1] - it[0][0]).length)
        n = len(items)
        cols = self.columns if self.columns > 0 else max(1, int(math.ceil(math.sqrt(n))))
        cell_x = max((mx.x - mn.x) for (mn, mx), _ in items) + self.spacing
        cell_y = max((mx.y - mn.y) for (mn, mx), _ in items) + self.spacing
        for i, ((mn, mx), ob) in enumerate(items):
            row, col_i = divmod(i, cols)
            tx = col_i * cell_x - mn.x
            ty = row * cell_y - mn.y
            vec = Vector((tx, ty, 0.0))
            if self.ground:
                vec.z = -mn.z
            cu.translate_world(ob, vec)
        self.report({'INFO'}, "已排布 %d 个物体（%d 列）" % (n, cols))
        return {'FINISHED'}


# ---------------------------------------------------------------- 网格打包（紧密堆积）
class LABOR_OT_shelf_pack(bpy.types.Operator):
    """把所选物体按占地轮廓紧密堆积到原点附近（支持随机旋转提高填充率）"""
    bl_idname = "labor.shelf_pack"
    bl_label = "紧密打包 (Shelf Pack)"
    bl_options = {'REGISTER', 'UNDO'}

    spacing: FloatProperty(name="间距倍数", description="物体之间的额外间隙", default=0.1,
                           min=0.0, precision=4)
    random_rot: IntProperty(name="随机旋转(%)", description="按百分比随机把物体转 90°",
                            default=0, min=0, max=100)
    ground: BoolProperty(name="底部落地", default=True)

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        rng = random.Random()
        items = [(cu.world_bbox(o), o) for o in context.selected_objects]
        # 计算占地（宽 x 深），可随机转 90°
        prints = []
        for (mn, mx), ob in items:
            w, d = mx.x - mn.x, mx.y - mn.y
            if self.random_rot > 0 and rng.randint(0, 100) <= self.random_rot:
                w, d = d, w
            prints.append([w, d, mn, mx, ob])
        prints.sort(key=lambda p: -max(p[0], p[1]))
        total_area = sum(p[0] * p[1] for p in prints)
        limit = math.sqrt(total_area) * 1.2 + max(p[0] for p in prints)
        cursor_x = cursor_y = row_h = 0.0
        origin_offset = Vector((0.0, 0.0, 0.0))
        first = True
        for w, d, mn, mx, ob in prints:
            if not first and cursor_x + w > limit:
                cursor_y += row_h + self.spacing
                cursor_x = 0.0
                row_h = 0.0
            vec = Vector((cursor_x - mn.x, cursor_y - mn.y, 0.0))
            if self.ground:
                vec.z = -mn.z
            cu.translate_world(ob, vec)
            cursor_x += w + self.spacing
            row_h = max(row_h, d)
            first = False
        self.report({'INFO'}, "已打包 %d 个物体" % len(prints))
        return {'FINISHED'}


class LABOR_PT_pack(bpy.types.Panel):
    bl_label = "网格排布 · 打包"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 6

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator(LABOR_OT_grid_pack.bl_idname, icon='GRID')
        col.operator(LABOR_OT_shelf_pack.bl_idname, icon='PACKAGE')


CLASSES = (LABOR_OT_grid_pack, LABOR_OT_shelf_pack, LABOR_PT_pack)
