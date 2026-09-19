# -*- coding: utf-8 -*-
"""blender_labor.ops_painter — 绘制（笔刷式摆放）
模态操作符：以活动物体为"画笔"，在表面点击即盖印关联副本。
Blender 原生没有对象绘制摆放工具，此模块完整移植 AssemblyTool Painter 的核心能力。
"""

import bpy
import random
from math import radians
from mathutils import Vector, Matrix, Euler
from bpy.props import FloatProperty, BoolProperty, PointerProperty
from bpy_extras import view3d_utils

from . import core_utils as cu


class LABOR_PainterSettings(bpy.types.PropertyGroup):
    offset: FloatProperty(name="偏移", description="沿法线方向抬升", default=0.0, precision=4)
    spacing: FloatProperty(name="间距", description="两次盖印之间的最小距离（0 = 不限制）",
                           default=0.0, precision=4)
    align_normal: BoolProperty(name="法线对齐", description="贴合表面法线", default=True)
    rot_max: FloatProperty(name="随机旋转(°)", description="每次盖印绕 Z 轴随机旋转最大角度",
                           default=0.0, soft_min=0.0, soft_max=180.0)
    scale_min: FloatProperty(name="缩放最小", default=1.0, soft_min=0.01)
    scale_max: FloatProperty(name="缩放最大", default=1.0, soft_min=0.01)


class LABOR_OT_paint(bpy.types.Operator):
    """笔刷绘制：移动鼠标预览，左键盖印副本，右键 / Esc 结束"""
    bl_idname = "labor.paint"
    bl_label = "绘制 (Paint)"
    bl_options = {'REGISTER'}

    _rst = None  # 随机数生成器

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        if context.area and context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "请在 3D 视口中使用绘制")
            return {'CANCELLED'}
        self.src = context.active_object
        self.orig_matrix = self.src.matrix_world.copy()
        self.base_quat = self.src.matrix_world.to_quaternion()
        self.last_loc = None
        self.placed = []
        self._rst = random.Random()
        self.settings = context.scene.labor_painter
        context.window.cursor_modal_set('PAINT_BRUSH')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _ray_from_mouse(self, context, event):
        region = context.region
        rv3d = context.region_data
        if region is None or rv3d is None:
            return None, None
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        hit, loc, n, obj = cu.scene_ray(context, origin, direction, exclude=[self.src])
        if hit:
            return loc, n
        # 未命中时投影到 Z=0 平面
        if abs(direction.z) > 1e-6:
            t = -origin.z / direction.z
            if t > 0:
                return origin + direction * t, Vector((0, 0, 1))
        return None, None

    def _move_brush(self, context, event):
        loc, n = self._ray_from_mouse(context, event)
        if loc is None:
            return
        s = self.settings
        if s.align_normal:
            q = n.to_track_quat('Z', 'Y')
            pos = loc + n * s.offset
        else:
            q = self.base_quat
            pos = loc + Vector((0, 0, s.offset))
        m = Matrix.LocRotScale(pos, q, None)
        self.src.matrix_world = m

    def _stamp(self, context, event):
        s = self.settings
        loc = self.src.matrix_world.translation
        if s.spacing > 0 and self.last_loc is not None:
            if (loc - self.last_loc).length < s.spacing:
                return
        dup = cu.linked_duplicate(context, self.src)
        m = self.src.matrix_world.copy()
        if s.rot_max > 0:
            ang = radians(self._rst.uniform(-s.rot_max, s.rot_max))
            m = m @ Matrix.Rotation(ang, 4, 'Z')
        if s.scale_max != s.scale_min:
            sc = self._rst.uniform(s.scale_min, s.scale_max)
            m = m @ Matrix.Diagonal(Vector((sc, sc, sc, 1.0)))
        dup.matrix_world = m
        self.last_loc = loc
        self.placed.append(dup)

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._move_brush(context, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._stamp(context, event)
            return {'RUNNING_MODAL'}
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self._finish(context)
            return {'FINISHED'}
        # 允许中途调整视角
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.value == 'PRESS' and event.type not in {'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        # 恢复画笔原位，选中所有盖印结果
        self.src.matrix_world = self.orig_matrix
        context.window.cursor_modal_restore()
        if self.placed:
            cu.select_only(context, self.placed)
            self.report({'INFO'}, "绘制了 %d 个物体" % len(self.placed))

    def cancel(self, context):
        if hasattr(self, 'orig_matrix'):
            self.src.matrix_world = self.orig_matrix
        context.window.cursor_modal_restore()


class LABOR_PT_painter(bpy.types.Panel):
    bl_label = "绘制（笔刷摆放）"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 2

    def draw(self, context):
        s = context.scene.labor_painter
        col = self.layout.column(align=True)
        col.label(text="以活动物体为画笔：", icon='BRUSHES_ALL')
        col.operator(LABOR_OT_paint.bl_idname, icon='MOD_PARTICLES')
        col.separator()
        col.prop(s, "offset")
        col.prop(s, "spacing")
        col.prop(s, "align_normal")
        col.prop(s, "rot_max")
        row = col.row(align=True)
        row.prop(s, "scale_min")
        row.prop(s, "scale_max")


CLASSES = (LABOR_PainterSettings, LABOR_OT_paint, LABOR_PT_painter)
