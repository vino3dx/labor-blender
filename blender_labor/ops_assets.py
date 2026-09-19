# -*- coding: utf-8 -*-
"""blender_labor.ops_assets — 资产整理（Labor 1.2 / 1.3 阶段）
整合用户脚本（物体各自建集合 / 归位原点 / 材质重命名 / 替换材质 / 清空插槽，
均为强化版）+ 路线图功能：批量标准化、重复网格检测、资产体检。
"""

import bpy
import os
import re
from mathutils import Vector, Matrix
from bpy.props import (BoolProperty, EnumProperty, IntProperty, FloatProperty,
                       StringProperty)

from . import core_utils as cu


# ================================================================ 材质工具
class LABOR_OT_rename_materials(bpy.types.Operator):
    """把所选物体的材质重命名为 物体名_序号（整合自用户脚本，增加去后缀选项）"""
    bl_idname = "labor.rename_materials"
    bl_label = "材质按物体重命名"
    bl_options = {'REGISTER', 'UNDO'}

    separator: StringProperty(name="分隔符", default="_")
    include_index: BoolProperty(name="添加序号", default=True)
    strip_suffix: BoolProperty(name="清理物体名后缀", description="去掉物体名末尾的 .001 式后缀",
                               default=True)

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        n = 0
        for ob in context.selected_objects:
            if ob.type != 'MESH':
                continue
            base = ob.name
            if self.strip_suffix:
                base = re.sub(r'\.\d{3}$', '', base)
            for idx, slot in enumerate(ob.material_slots):
                if slot.material:
                    suffix = "%s%d" % (self.separator, idx) if self.include_index else ""
                    slot.material.name = base + suffix
                    n += 1
        self.report({'INFO'}, "重命名了 %d 个材质" % n)
        return {'FINISHED'}


class LABOR_OT_replace_material(bpy.types.Operator):
    """把所选物体的材质快速替换为活动物体的当前材质（导入乱模型的救星）"""
    bl_idname = "labor.replace_material"
    bl_label = "快速替换材质"
    bl_options = {'REGISTER', 'UNDO'}

    scope: EnumProperty(
        name="替换范围",
        items=(('ALL', "所有材质槽", "物体所有槽都换成目标材质"),
               ('FIRST', "仅第一个槽", "只替换第一个槽，保留其余槽")),
        default='ALL',
    )
    remove_extra: BoolProperty(name="删除多余槽", description="仅替换第一槽时是否删除其余空槽",
                               default=False)

    @classmethod
    def poll(cls, context):
        act = context.active_object
        return (act is not None and act.type == 'MESH'
                and act.active_material is not None
                and len([o for o in context.selected_objects if o is not act]) >= 1)

    def execute(self, context):
        mat = context.active_object.active_material
        targets = [o for o in context.selected_objects
                   if o is not context.active_object and o.type == 'MESH']
        for ob in targets:
            if self.scope == 'ALL':
                for slot in ob.material_slots:
                    slot.material = mat
            else:
                if not ob.material_slots:
                    ob.data.materials.append(mat)
                else:
                    ob.material_slots[0].material = mat
                    if self.remove_extra:
                        ob.data.materials.clear()
                        ob.data.materials.append(mat)
        self.report({'INFO'}, "已把 %d 个物体的材质替换为 %s" % (len(targets), mat.name))
        return {'FINISHED'}


class LABOR_OT_clean_empty_slots(bpy.types.Operator):
    """清除所选物体上没有分配材质的空材质槽（整合自用户脚本）"""
    bl_idname = "labor.clean_empty_slots"
    bl_label = "清除空材质槽"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        n = 0
        for ob in meshes:
            for i in range(len(ob.material_slots) - 1, -1, -1):
                if ob.material_slots[i].material is None:
                    ob.active_material_index = i
                    with context.temp_override(object=ob, active_object=ob,
                                               selected_objects=[ob],
                                               selected_editable_objects=[ob]):
                        bpy.ops.object.material_slot_remove()
                    n += 1
        self.report({'INFO'}, "清除了 %d 个空材质槽" % n)
        return {'FINISHED'}


# ================================================================ 物体整理
class LABOR_OT_move_to_own_collection(bpy.types.Operator):
    """把每个所选物体移入以自己命名的新集合（整合自用户脚本，增加跳过选项）"""
    bl_idname = "labor.move_to_own_collection"
    bl_label = "物体各自建集合"
    bl_options = {'REGISTER', 'UNDO'}

    skip_alone: BoolProperty(name="跳过独占集合的物体", description="物体所在集合只有它自己时不重建",
                             default=True)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        n = skip = 0
        for ob in context.selected_objects:
            colls = list(ob.users_collection)
            if self.skip_alone and len(colls) == 1 and len(colls[0].objects) == 1:
                skip += 1
                continue
            coll = bpy.data.collections.new(ob.name)
            context.scene.collection.children.link(coll)
            for c in colls:
                c.objects.unlink(ob)
            coll.objects.link(ob)
            n += 1
        self.report({'INFO'}, "建了 %d 个集合（跳过 %d）" % (n, skip))
        return {'FINISHED'}


class LABOR_OT_home_to_origin(bpy.types.Operator):
    """归位到原点（整合自用户脚本，增加"底部中心对齐世界原点"模式）"""
    bl_idname = "labor.home_to_origin"
    bl_label = "归位到原点"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="模式",
        items=(('LOCATION', "物体原点归零", "location 设为 (0,0,0)（原脚本行为）"),
               ('BOTTOM', "底部中心对齐世界原点", "包围盒底部中心移到世界原点，适合按原点摆放资产")),
        default='BOTTOM',
    )

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            if self.mode == 'LOCATION':
                ob.location = (0.0, 0.0, 0.0)
            else:
                mn, mx = cu.world_bbox(ob)
                P = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
                cu.translate_world(ob, -P)
        return {'FINISHED'}


# ================================================================ 批量标准化
class LABOR_OT_batch_standardize(bpy.types.Operator):
    """批量标准化导入资产：旋转归零 / 缩放统一 / 原点到底部中心 / 底部落地
    （下载资产、Kitbash 资产混杂 rotation/scale 时一键洗干净）"""
    bl_idname = "labor.batch_standardize"
    bl_label = "批量标准化 (Standardize)"
    bl_options = {'REGISTER', 'UNDO'}

    zero_rotation: BoolProperty(name="旋转归零（烘焙到网格）", default=True)
    uniform_scale: BoolProperty(name="缩放统一为 1（烘焙到网格）", default=True)
    origin_bottom: BoolProperty(name="原点到底部中心", default=True)
    ground: BoolProperty(name="底部落地 (Z=0)", default=True)

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        for ob in meshes:
            cu.make_single_user_data(ob)
            if self.zero_rotation or self.uniform_scale:
                with context.temp_override(active_object=ob, selected_objects=[ob],
                                           selected_editable_objects=[ob]):
                    bpy.ops.object.transform_apply(location=False,
                                                   rotation=self.zero_rotation,
                                                   scale=self.uniform_scale)
            if self.origin_bottom:
                cu.move_origin_to_bottom(ob)
            if self.ground:
                mn, _mx = cu.world_bbox(ob)
                cu.translate_world(ob, Vector((0, 0, -mn.z)))
        self.report({'INFO'}, "标准化了 %d 个物体" % len(meshes))
        return {'FINISHED'}


# ================================================================ 重复网格检测
def _dup_mesh_groups(context):
    groups = {}
    for ob in context.scene.objects:
        if ob.type == 'MESH' and ob.data:
            groups.setdefault(ob.data.name, []).append(ob)
    return [g for g in groups.values() if len(g) > 1]


class LABOR_OT_select_dup_meshes(bpy.types.Operator):
    """选中所有共享同一网格数据的重复物体（每组保留一个；纯几何重复用"网格→使其唯一"反向处理）"""
    bl_idname = "labor.select_dup_meshes"
    bl_label = "选择重复网格（保留一个）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        groups = _dup_mesh_groups(context)
        dups = []
        for g in groups:
            dups.extend(g[1:])
        if not dups:
            self.report({'INFO'}, "没有共享网格数据的重复物体")
            return {'CANCELLED'}
        cu.select_only(context, dups)
        self.report({'INFO'}, "发现 %d 组重复，选中 %d 个多余副本" % (len(groups), len(dups)))
        return {'FINISHED'}


class LABOR_OT_delete_dup_meshes(bpy.types.Operator):
    """删除共享同一网格数据的重复物体（每组保留一个）"""
    bl_idname = "labor.delete_dup_meshes"
    bl_label = "删除重复网格（保留一个）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        groups = _dup_mesh_groups(context)
        dups = []
        for g in groups:
            dups.extend(g[1:])
        if not dups:
            self.report({'INFO'}, "没有共享网格数据的重复物体")
            return {'CANCELLED'}
        cu.delete_objects(context, dups)
        self.report({'INFO'}, "删除了 %d 个重复物体（共 %d 组）" % (len(dups), len(groups)))
        return {'FINISHED'}


# ================================================================ 资产体检
class LABOR_OT_asset_checkup(bpy.types.Operator):
    """一键扫描场景资产健康度：缺失贴图 / 大贴图 / 重复材质 / 未使用材质 /
    空物体 / 高面数物体 / 重复网格；可把问题物体直接选中"""
    bl_idname = "labor.asset_checkup"
    bl_label = "资产体检 (Checkup)"
    bl_options = {'REGISTER'}

    big_texture: IntProperty(name="大贴图阈值(px)", default=4096, min=2)
    high_poly: IntProperty(name="高面数阈值", default=100000, min=1)
    select_problems: BoolProperty(name="选中问题物体", default=True)

    @classmethod
    def poll(cls, context):
        return True

    def _missing_images(self):
        missing = set()
        for img in bpy.data.images:
            if img.source != 'FILE' or img.packed_file is not None:
                continue
            if not img.filepath:
                missing.add(img.name)
                continue
            if not os.path.exists(bpy.path.abspath(img.filepath)):
                missing.add(img.name)
        return missing

    def _objects_using_images(self, img_names):
        img_names = set(img_names)
        result = set()
        for ob in bpy.data.objects:
            if ob.type != 'MESH':
                continue
            for slot in ob.material_slots:
                m = slot.material
                if not m or not m.use_nodes:
                    continue
                for node in m.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name in img_names:
                        result.add(ob)
        return result

    def execute(self, context):
        lines = []
        problem_objs = set()

        # 1. 缺失贴图
        missing = self._missing_images()
        if missing:
            users = self._objects_using_images(missing)
            problem_objs |= users
            lines.append("缺失贴图: %d 张 → 涉及 %d 个物体" % (len(missing), len(users)))
        else:
            lines.append("缺失贴图: 0")

        # 2. 大贴图
        big = [img.name for img in bpy.data.images
               if img.source == 'FILE' and img.size[0] >= self.big_texture]
        lines.append("大贴图 (≥%dpx): %d 张%s" % (self.big_texture, len(big),
                                                 ("：" + ", ".join(big[:8])) if big else ""))

        # 3. 重复材质（.001 命名组）
        base_map = {}
        for m in bpy.data.materials:
            base_map.setdefault(re.sub(r'\.\d{3}$', '', m.name), []).append(m.name)
        dup_mats = {k: v for k, v in base_map.items() if len(v) > 1}
        lines.append("重复材质: %d 组" % len(dup_mats))

        # 4. 未使用材质
        unused = [m.name for m in bpy.data.materials if m.users == 0]
        lines.append("未使用材质: %d 个" % len(unused))

        # 5. 空网格物体
        empties = [o for o in bpy.data.objects
                   if o.type == 'MESH' and o.data and len(o.data.vertices) == 0]
        problem_objs |= set(empties)
        lines.append("空网格物体: %d 个" % len(empties))

        # 6. 高面数物体
        highs = [o for o in bpy.data.objects
                 if o.type == 'MESH' and o.data and len(o.data.polygons) >= self.high_poly]
        problem_objs |= set(highs)
        lines.append("高面数 (≥%d): %d 个" % (self.high_poly, len(highs)))

        # 7. 重复网格数据
        groups = _dup_mesh_groups(context)
        lines.append("重复网格数据: %d 组" % len(groups))

        for ln in lines:
            print("Labor 体检 | " + ln)
        self.report({'INFO'}, "体检完成：" + " ｜ ".join(l.split(":")[0] for l in lines[:4]) +
                    " … 详情见系统控制台")
        if self.select_problems and problem_objs:
            cu.select_only(context, list(problem_objs))
        return {'FINISHED'}


# ================================================================ 面板
class LABOR_PT_assets(bpy.types.Panel):
    bl_label = "资产整理"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 10

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="材质：", icon='MATERIAL')
        col.operator(LABOR_OT_rename_materials.bl_idname, icon='FONT_DATA')
        col.operator(LABOR_OT_replace_material.bl_idname, icon='COPYDOWN')
        col.operator(LABOR_OT_clean_empty_slots.bl_idname, icon='X')
        col.separator()
        col.label(text="物体：", icon='OBJECT_DATAMODE')
        col.operator(LABOR_OT_move_to_own_collection.bl_idname, icon='OUTLINER_COLLECTION')
        col.operator(LABOR_OT_home_to_origin.bl_idname, icon='OBJECT_ORIGIN')
        col.operator(LABOR_OT_batch_standardize.bl_idname, icon='CHECKMARK')
        col.separator()
        col.label(text="重复与体检：", icon='ZOOM_SELECTED')
        row = col.row(align=True)
        row.operator(LABOR_OT_select_dup_meshes.bl_idname, text="选重复")
        row.operator(LABOR_OT_delete_dup_meshes.bl_idname, text="删重复")
        col.operator(LABOR_OT_asset_checkup.bl_idname, icon='MODIFIER_ON')


CLASSES = (LABOR_OT_rename_materials, LABOR_OT_replace_material, LABOR_OT_clean_empty_slots,
           LABOR_OT_move_to_own_collection, LABOR_OT_home_to_origin,
           LABOR_OT_batch_standardize, LABOR_OT_select_dup_meshes, LABOR_OT_delete_dup_meshes,
           LABOR_OT_asset_checkup, LABOR_PT_assets)
