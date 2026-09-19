# -*- coding: utf-8 -*-
"""blender_labor.ops_group — 自动成组 / 虚拟体（空物体）放置
（Blender 原生 Ctrl+G 成组/建集合已覆盖常规组操作；本模块移植 Max 特有的
   「按距离自动成组」与「按包围盒创建虚拟体」）
"""

import bpy
import math
from mathutils import Vector
from bpy.props import FloatProperty, StringProperty, BoolProperty, EnumProperty, IntProperty

from . import core_utils as cu


# ---------------------------------------------------------------- 自动成组
class LABOR_OT_auto_group(bpy.types.Operator):
    """按距离容差自动把彼此靠近的所选物体分入不同集合（先预览可减小容差试错）"""
    bl_idname = "labor.auto_group"
    bl_label = "自动成组 (Auto Group)"
    bl_options = {'REGISTER', 'UNDO'}

    tolerance: FloatProperty(name="检测容差", description="包围盒间隙小于该值视为同一组",
                             default=0.2, min=0.0, precision=4)
    prefix: StringProperty(name="集合前缀", default="AutoGroup_")
    name_from_object: BoolProperty(name="用物体名命名", description="用组内第一个物体命名集合",
                                   default=False)

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def execute(self, context):
        objs = [o for o in context.selected_objects]
        boxes = [(o, cu.world_bbox(o)) for o in objs]
        tol = self.tolerance
        clusters = []  # [{'objs': [...], 'mn': V, 'mx': V}]
        for ob, (mn, mx) in boxes:
            best, best_d = None, None
            for c in clusters:
                d = cu.bbox_gap(mn, mx, c['mn'], c['mx'])
                if d <= tol and (best is None or d < best_d):
                    best, best_d = c, d
            if best is not None:
                best['objs'].append(ob)
                best['mn'] = Vector((min(best['mn'][i], mn[i]) for i in range(3)))
                best['mx'] = Vector((max(best['mx'][i], mx[i]) for i in range(3)))
            else:
                clusters.append({'objs': [ob], 'mn': Vector(mn), 'mx': Vector(mx)})
        scene_coll = context.scene.collection
        for i, c in enumerate(clusters):
            if self.name_from_object:
                name = c['objs'][0].name
            else:
                name = "%s%03d" % (self.prefix, i + 1)
            coll = bpy.data.collections.new(name)
            scene_coll.children.link(coll)
            for ob in c['objs']:
                for oc in list(ob.users_collection):
                    oc.objects.unlink(ob)
                coll.objects.link(ob)
        self.report({'INFO'}, "自动分成了 %d 组" % len(clusters))
        return {'FINISHED'}


# ---------------------------------------------------------------- 虚拟体（空物体）放置
class LABOR_OT_empty_placer(bpy.types.Operator):
    """为所选物体按包围盒创建适配尺寸的空物体（可用于导出占位、控制点）"""
    bl_idname = "labor.empty_placer"
    bl_label = "创建适配空物体 (Dummy)"
    bl_options = {'REGISTER', 'UNDO'}

    location: EnumProperty(
        name="位置",
        items=(('CENTER', "包围盒中心", ""), ('BOTTOM', "底部中心（Z 最小）", "")),
        default='BOTTOM',
    )
    fixed_size: FloatProperty(name="固定显示尺寸", description="0 = 按包围盒自动",
                              default=0.0, min=0.0)
    link_children: BoolProperty(name="父子级链接", description="创建后把所选物体父级到空物体",
                                default=False)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        objs = list(context.selected_objects)
        mn, mx = cu.world_bbox(objs[0])
        for ob in objs[1:]:
            om, ox = cu.world_bbox(ob)
            mn = Vector((min(mn[i], om[i]) for i in range(3)))
            mx = Vector((max(mx[i], ox[i]) for i in range(3)))
        size = max((mx - mn).length, 0.001)
        if self.location == 'BOTTOM':
            loc = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
        else:
            loc = (mn + mx) / 2
        empty = bpy.data.objects.new("Dummy_" + objs[0].name, None)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = self.fixed_size if self.fixed_size > 0 else size / 2
        empty.location = loc
        context.collection.objects.link(empty)
        if self.link_children:
            inv = empty.matrix_world.inverted()
            for ob in objs:
                if ob.parent is None:
                    ob.parent = empty
                    ob.matrix_parent_inverse = inv.copy()
        cu.select_only(context, [empty])
        return {'FINISHED'}


class LABOR_PT_group(bpy.types.Panel):
    bl_label = "自动成组 · 虚拟体"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 5

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="按距离自动分组：", icon='OUTLINER_COLLECTION')
        col.operator(LABOR_OT_auto_group.bl_idname)
        col.separator()
        col.label(text="虚拟体（空物体）：", icon='EMPTY_AXIS')
        col.operator(LABOR_OT_empty_placer.bl_idname)
        col.label(text="常规成组/父级请用 Ctrl+G、Ctrl+P。", icon='INFO')


CLASSES = (LABOR_OT_auto_group, LABOR_OT_empty_placer, LABOR_PT_group)
