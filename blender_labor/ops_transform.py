# -*- coding: utf-8 -*-
"""blender_labor.ops_transform — 下落 / 快速对齐 / 线性间距 / 重叠检测 / 放置到表面
（对应 AssemblyTool「变换」卷展栏中 Blender 缺失的部分；
   普通旋转、常规对齐等 Blender 已原生支持，不移植）
"""

import bpy
import random
from math import radians
from mathutils import Vector, Matrix
from bpy.props import EnumProperty, FloatProperty, BoolProperty, IntProperty

from . import core_utils as cu


# ---------------------------------------------------------------- 下落
class LABOR_OT_drop(bpy.types.Operator):
    """把所选物体垂直下落到下方表面或世界地面（Z=0）"""
    bl_idname = "labor.drop_to_ground"
    bl_label = "下落 (Drop)"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="模式",
        items=(
            ('SCENE', "下落到场景", "射线检测下方场景表面并落上去"),
            ('GROUND', "下落到地面 (Z=0)", "直接落到世界 Z=0 平面"),
        ),
        default='SCENE',
    )
    offset: FloatProperty(name="偏移", description="落点沿法线/竖直方向的抬高距离",
                          default=0.0, precision=4)
    align_normal: BoolProperty(name="法线对齐", description="下落后贴合表面法线方向",
                               default=False)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        dropped = 0
        for ob in context.selected_objects:
            mn, mx = cu.world_bbox(ob)
            hit = False
            n = Vector((0, 0, 1))
            if self.mode == 'GROUND':
                dz = self.offset - mn.z
            else:
                exclude = [ob] + cu.children_recursive(ob)
                origin = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mx.z + 0.5))
                hit, loc, n, hobj = cu.scene_ray(context, origin, Vector((0, 0, -1)), exclude)
                if not hit:
                    continue
                dz = (loc.z + self.offset) - mn.z
            cu.translate_world(ob, Vector((0, 0, dz)))
            if self.align_normal and hit:
                # 绕包围盒中心旋转，使物体 Z 轴贴合法线
                center = (mn + mx) / 2
                q = n.to_track_quat('Z', 'Y').to_matrix().to_4x4()
                ob.matrix_world = (Matrix.Translation(center) @ q @
                                   Matrix.Translation(-center) @ ob.matrix_world)
            dropped += 1
        self.report({'INFO'}, "已下落 %d 个物体" % dropped)
        return {'FINISHED'}


# ---------------------------------------------------------------- 快速对齐
class LABOR_OT_quick_align(bpy.types.Operator):
    """把所选物体沿指定轴对齐到活动物体的 最小值 / 中心 / 最大值"""
    bl_idname = "labor.quick_align"
    bl_label = "快速对齐 (Quick Align)"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name="轴", items=(('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")),
                       default='Z')
    mode: EnumProperty(
        name="对齐到",
        items=(('MIN', "最小", "对齐到活动物体包围盒最小值"),
               ('CENTER', "中心", "对齐到活动物体包围盒中心"),
               ('MAX', "最大", "对齐到活动物体包围盒最大值")),
        default='MIN',
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and len(context.selected_objects) >= 2

    def execute(self, context):
        act = context.active_object
        ai = 'XYZ'.index(self.axis)
        a_mn, a_mx = cu.world_bbox(act)
        if self.mode == 'MIN':
            target = a_mn[ai]
        elif self.mode == 'MAX':
            target = a_mx[ai]
        else:
            target = (a_mn[ai] + a_mx[ai]) / 2
        for ob in context.selected_objects:
            if ob is act:
                continue
            mn, mx = cu.world_bbox(ob)
            cur = mn[ai] if self.mode == 'MIN' else (mx[ai] if self.mode == 'MAX'
                                                    else (mn[ai] + mx[ai]) / 2)
            vec = Vector((0, 0, 0))
            vec[ai] = target - cur
            cu.translate_world(ob, vec)
        return {'FINISHED'}


# ---------------------------------------------------------------- 线性间距
class LABOR_OT_linear_spacing(bpy.types.Operator):
    """把所选物体沿指定轴等间距重新排列（第一个物体不动）"""
    bl_idname = "labor.linear_spacing"
    bl_label = "等距排列 (Spacing)"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name="轴", items=(('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")),
                       default='X')
    gap: FloatProperty(name="间距", description="相邻物体包围盒之间的距离", default=0.5,
                       precision=4)
    order: EnumProperty(name="排序", items=(('ASC', "递增", "按位置递增排列"),
                                            ('DESC', "递减", "按位置递减排列")),
                        default='ASC')

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        ai = 'XYZ'.index(self.axis)
        items = [(cu.world_bbox(ob), ob) for ob in context.selected_objects]
        items.sort(key=lambda it: it[0][0][ai])
        anchor = items[0][0][0][ai]
        if self.order == 'DESC':
            items.reverse()
        cursor = anchor
        for (mn, mx), ob in items:
            vec = Vector((0, 0, 0))
            vec[ai] = cursor - mn[ai]
            cu.translate_world(ob, vec)
            cursor += (mx - mn)[ai] + self.gap
        return {'FINISHED'}


# ---------------------------------------------------------------- 重叠检测
class LABOR_OT_select_overlapping(bpy.types.Operator):
    """在所选物体中找出与其它物体包围盒相交的物体并选中（用于快速清理穿插）"""
    bl_idname = "labor.select_overlapping"
    bl_label = "选择重叠物体"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        objs = [o for o in context.selected_objects]
        boxes = [(o, cu.world_bbox(o)) for o in objs]
        overlap = set()
        for i in range(len(boxes)):
            oi, (mni, mxi) = boxes[i]
            for j in range(i + 1, len(boxes)):
                oj, (mnj, mxj) = boxes[j]
                if cu.bbox_gap(mni, mxi, mnj, mxj) == 0.0:
                    overlap.add(oi)
                    overlap.add(oj)
        if not overlap:
            self.report({'INFO'}, "没有发现重叠物体")
            return {'CANCELLED'}
        cu.select_only(context, list(overlap))
        self.report({'INFO'}, "发现 %d 个重叠物体" % len(overlap))
        return {'FINISHED'}


# ---------------------------------------------------------------- 放置到表面
class LABOR_OT_place_on_surface(bpy.types.Operator):
    """把所选物体原地放置到活动物体（最后选的）表面——不复制，是"散布"的移动版；
    保持各自水平位置，沿竖直方向落到目标表面上"""
    bl_idname = "labor.place_on_surface"
    bl_label = "放置到表面 (Place on Surface)"
    bl_options = {'REGISTER', 'UNDO'}

    align_normal: BoolProperty(name="法线对齐", description="贴合表面法线（可关掉保持 Z 轴竖直）",
                               default=False)
    offset: FloatProperty(name="偏移", default=0.0, precision=4)
    random_rot_z: FloatProperty(name="随机旋转(°)", default=0.0, soft_min=0.0, soft_max=180.0)
    random_scale: BoolProperty(name="随机缩放", default=False)
    scale_min: FloatProperty(name="缩放最小", default=0.9, soft_min=0.01)
    scale_max: FloatProperty(name="缩放最大", default=1.1, soft_min=0.01)
    seed: IntProperty(name="随机种子", default=0)

    @classmethod
    def poll(cls, context):
        act = context.active_object
        return (act is not None and act.type == 'MESH'
                and len([o for o in context.selected_objects if o is not act]) >= 1)

    def execute(self, context):
        surface = context.active_object
        targets = [o for o in context.selected_objects if o is not surface]
        exclude = []
        for ob in targets:
            exclude.append(ob)
            exclude.extend(cu.children_recursive(ob))
        rng = random.Random(self.seed)
        placed = 0
        for ob in targets:
            mn, mx = cu.world_bbox(ob)
            origin = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mx.z + 0.5))
            hit, loc, n, hobj = cu.scene_ray(context, origin, Vector((0, 0, -1)), exclude)
            if not hit:
                continue
            cu.translate_world(ob, Vector((0, 0, (loc.z + self.offset) - mn.z)))
            if self.align_normal:
                center = (mn + mx) / 2
                q = n.to_track_quat('Z', 'Y').to_matrix().to_4x4()
                ob.matrix_world = (Matrix.Translation(center) @ q @
                                   Matrix.Translation(-center) @ ob.matrix_world)
            if self.random_rot_z > 0:
                ang = radians(rng.uniform(-self.random_rot_z, self.random_rot_z))
                ob.matrix_world = ob.matrix_world @ Matrix.Rotation(ang, 4, 'Z')
            if self.random_scale:
                s = rng.uniform(self.scale_min, self.scale_max)
                P = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
                S = Matrix.Diagonal(Vector((s, s, s, 1.0)))
                ob.matrix_world = (Matrix.Translation(P) @ S @
                                   Matrix.Translation(-P) @ ob.matrix_world)
            placed += 1
        self.report({'INFO'}, "放置了 %d / %d 个物体" % (placed, len(targets)))
        return {'FINISHED'}


# ---------------------------------------------------------------- 面板
class LABOR_PT_transform(bpy.types.Panel):
    bl_label = "下落 · 对齐 · 间距"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 0

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="下落：", icon='TRIA_DOWN')
        col.operator(LABOR_OT_drop.bl_idname, text="下落到场景").mode = 'SCENE'
        col.operator(LABOR_OT_drop.bl_idname, text="下落到地面 Z=0").mode = 'GROUND'
        op = col.operator(LABOR_OT_place_on_surface.bl_idname, text="放置到表面（移动版散布）")
        col.separator()
        col.label(text="快速对齐（到活动物体）：")
        op = col.operator(LABOR_OT_quick_align.bl_idname, text="X 最小")
        op.axis, op.mode = 'X', 'MIN'
        op = col.operator(LABOR_OT_quick_align.bl_idname, text="X 中心")
        op.axis, op.mode = 'X', 'CENTER'
        op = col.operator(LABOR_OT_quick_align.bl_idname, text="Z 最小（落地）")
        op.axis, op.mode = 'Z', 'MIN'
        op = col.operator(LABOR_OT_quick_align.bl_idname, text="Z 最大")
        op.axis, op.mode = 'Z', 'MAX'
        col.separator()
        col.label(text="等距排列：")
        op = col.operator(LABOR_OT_linear_spacing.bl_idname, text="沿 X 等距")
        op.axis, op.order = 'X', 'ASC'
        op = col.operator(LABOR_OT_linear_spacing.bl_idname, text="沿 Y 等距")
        op.axis, op.order = 'Y', 'ASC'
        col.separator()
        col.operator(LABOR_OT_select_overlapping.bl_idname, icon='X')


CLASSES = (LABOR_OT_drop, LABOR_OT_quick_align, LABOR_OT_linear_spacing,
           LABOR_OT_select_overlapping, LABOR_OT_place_on_surface, LABOR_PT_transform)
