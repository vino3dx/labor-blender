# -*- coding: utf-8 -*-
"""blender_labor.ops_community — 社区呼声 · 补缺功能
Blender 社区长期反馈缺失、且原生无对应实现的常见功能：
1. 圆周阵列          （阵列修改器只能线性）
2. 精确尺寸缩放      （把物体缩放到精确尺寸，可选保持底部不动）
3. 按尺寸/面数范围选择（原生"选择相似"只能选相同值，不能选范围）
4. 纹理密度 Texel Density（测量 + 设置，Blender 无原生工具）
5. 快速物理沉降      （刚体结算并烘焙为普通变换，免手动摆堆叠）
6. 场景清理          （删空物体 / 合并 .001 重复材质 / 清孤儿数据）
7. 原点到底部中心    （建筑可视化落地摆放刚需）
"""

import bpy
import re
import math
from mathutils import Vector, Matrix
from bpy.props import (IntProperty, FloatProperty, BoolProperty, EnumProperty,
                       FloatVectorProperty, StringProperty)

from . import core_utils as cu


# ================================================================ 圆周阵列
class LABOR_OT_circular_array(bpy.types.Operator):
    """把所选物体绕 3D 游标（或包围盒中心）做圆周阵列"""
    bl_idname = "labor.circular_array"
    bl_label = "圆周阵列 (Circular Array)"
    bl_options = {'REGISTER', 'UNDO'}

    count: IntProperty(name="总份数", description="圆周上的总份数（含原件）", default=8, min=2)
    axis: EnumProperty(name="旋转轴", items=(('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")),
                       default='Z')
    center: EnumProperty(name="圆心", items=(('CURSOR', "3D 游标", ""),
                                             ('BBOX', "所选包围盒中心", "")),
                         default='CURSOR')
    face_center: BoolProperty(name="朝向圆心", description="副本随阵列旋转朝向（放射状排列）",
                              default=True)
    linked_data: BoolProperty(name="关联数据", default=True)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        objs = [o for o in context.selected_objects]
        if self.center == 'BBOX':
            mn, mx = cu.world_bbox(objs[0])
            for ob in objs[1:]:
                om, ox = cu.world_bbox(ob)
                mn = Vector((min(mn[i], om[i]) for i in range(3)))
                mx = Vector((max(mx[i], ox[i]) for i in range(3)))
            center = (mn + mx) / 2
        else:
            center = context.scene.cursor.location.copy()
        ai = 'XYZ'.index(self.axis)
        basis = [i for i in range(3) if i != ai]  # 旋转平面上的两个轴
        step = 2 * math.pi / self.count
        results = []
        for base in objs:
            rel = base.matrix_world.translation - center
            rel_axis = Vector((rel[0], rel[1], rel[2]))
            plane_rel = Vector((rel[basis[0]], rel[basis[1]], 0.0))
            for i in range(1, self.count):
                ang = step * i
                ca, sa = math.cos(ang), math.sin(ang)
                # 在旋转平面内旋转相对位置
                px = plane_rel.x * ca - plane_rel.y * sa
                py = plane_rel.x * sa + plane_rel.y * ca
                new_rel = Vector((0.0, 0.0, 0.0))
                new_rel[basis[0]] = px
                new_rel[basis[1]] = py
                new_rel[ai] = rel[ai]
                if self.linked_data:
                    dup = cu.linked_duplicate(context, base)
                else:
                    dup = base.copy()
                    if base.data:
                        dup.data = base.data.copy()
                    context.collection.objects.link(dup)
                if self.face_center:
                    R = Matrix.Rotation(ang, 4, 'XYZ'[ai])
                    dup.matrix_world = (Matrix.Translation(center) @ R @
                                        Matrix.Translation(-center) @ base.matrix_world)
                else:
                    cu.translate_world(dup, new_rel - rel)
                results.append(dup)
        if results:
            cu.select_only(context, results)
            self.report({'INFO'}, "圆周阵列生成了 %d 个副本" % len(results))
        return {'FINISHED'}


# ================================================================ 精确尺寸缩放
class LABOR_OT_scale_to_size(bpy.types.Operator):
    """把所选物体缩放到精确的世界尺寸（以包围盒底部中心为基准，底部位置不动）"""
    bl_idname = "labor.scale_to_size"
    bl_label = "缩放到精确尺寸"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name="基准轴", items=(('LONGEST', "最长边", ""),
                                             ('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")),
                       default='Z')
    target: FloatProperty(name="目标尺寸", description="米", default=1.0, min=0.0001,
                          precision=4)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            mn, mx = cu.world_bbox(ob)
            dims = mx - mn
            ai = 'XYZ'.index(self.axis) if self.axis != 'LONGEST' else \
                max(range(3), key=lambda i: dims[i])
            if dims[ai] <= 1e-9:
                continue
            f = self.target / dims[ai]
            # 以包围盒底部中心为基准缩放（底部位置不动）
            P = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
            S = Matrix.Diagonal(Vector((f, f, f, 1.0)))
            ob.matrix_world = (Matrix.Translation(P) @ S @
                               Matrix.Translation(-P) @ ob.matrix_world)
        return {'FINISHED'}


# ================================================================ 按属性范围选择
class LABOR_OT_select_by_size(bpy.types.Operator):
    """按包围盒尺寸范围选择场景物体（例如选出所有小于 30cm 的小件）"""
    bl_idname = "labor.select_by_size"
    bl_label = "按尺寸范围选择"
    bl_options = {'REGISTER', 'UNDO'}

    min_d: FloatVectorProperty(name="最小尺寸", size=3, default=(0.0, 0.0, 0.0), precision=4)
    max_d: FloatVectorProperty(name="最大尺寸", size=3, default=(100.0, 100.0, 100.0),
                               precision=4)
    match_all: BoolProperty(name="三轴同时满足", description="关 = 任一轴在范围内即选中",
                            default=True)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        hits = []
        for ob in context.visible_objects:
            if ob.type not in {'MESH', 'CURVE'}:
                continue
            dims = Vector(cu.world_bbox(ob)[1]) - Vector(cu.world_bbox(ob)[0])
            ok_axis = [self.min_d[i] <= dims[i] <= self.max_d[i] for i in range(3)]
            if (all(ok_axis) if self.match_all else any(ok_axis)):
                hits.append(ob)
        if not hits:
            self.report({'INFO'}, "没有物体在尺寸范围内")
            return {'CANCELLED'}
        cu.select_only(context, hits)
        self.report({'INFO'}, "选中 %d 个物体" % len(hits))
        return {'FINISHED'}


class LABOR_OT_select_by_polys(bpy.types.Operator):
    """按面数范围选择场景物体（含修改器评估结果，例如揪出面数超标的"钉子户"）"""
    bl_idname = "labor.select_by_polys"
    bl_label = "按面数范围选择"
    bl_options = {'REGISTER', 'UNDO'}

    min_p: IntProperty(name="最小面数", default=0)
    max_p: IntProperty(name="最大面数", default=100000000)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        depsgraph = context.evaluated_depsgraph_get()
        hits = []
        for ob in context.visible_objects:
            if ob.type != 'MESH':
                continue
            ev = ob.evaluated_get(depsgraph)
            m = ev.to_mesh()
            n = len(m.polygons)
            ev.to_mesh_clear()
            if self.min_p <= n <= self.max_p:
                hits.append(ob)
        if not hits:
            self.report({'INFO'}, "没有物体在面数范围内")
            return {'CANCELLED'}
        cu.select_only(context, hits)
        self.report({'INFO'}, "选中 %d 个物体" % len(hits))
        return {'FINISHED'}


# ================================================================ 纹理密度
def _mesh_uv_data(mesh):
    """返回 (uv 层, uv 总面积, 岛屿列表)。岛屿 = [loop 索引列表]。"""
    uv = mesh.uv_layers.active or (mesh.uv_layers[0] if len(mesh.uv_layers) else None)
    if uv is None:
        return None, 0.0, []
    uvs = uv.data
    n = len(mesh.loops)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # UV 连续（非接缝）的边 → 同一岛屿
    edge_loops = {}
    for li in range(n):
        edge_loops.setdefault(mesh.loops[li].edge_index, []).append(li)
    for loops in edge_loops.values():
        if len(loops) == 2:
            a, b = loops
            if (uvs[a].uv - uvs[b].uv).length_squared < 1e-14:
                union(a, b)

    islands = {}
    for li in range(n):
        islands.setdefault(find(li), []).append(li)

    # UV 总面积（多边形扇形三角化）
    uv_area = 0.0
    for poly in mesh.polygons:
        ls = list(poly.loop_indices)
        if len(ls) < 3:
            continue
        p0 = uvs[ls[0]].uv
        for i in range(1, len(ls) - 1):
            e1 = uvs[ls[i]].uv - p0
            e2 = uvs[ls[i + 1]].uv - p0
            uv_area += abs(e1.x * e2.y - e1.y * e2.x) * 0.5
    return uv, uv_area, list(islands.values())


def _mesh_world_area(ob):
    """世界空间表面积（局部面积 × 中位缩放²，近似值）。"""
    area = sum(p.area for p in ob.data.polygons)
    return area * (ob.matrix_world.median_scale ** 2)


class LABOR_OT_texel_density_measure(bpy.types.Operator):
    """测量所选物体的纹理密度（像素/米，基于活动 UV 通道与参考贴图尺寸）"""
    bl_idname = "labor.texel_density_measure"
    bl_label = "测量纹理密度"
    bl_options = {'REGISTER'}

    ref_size: IntProperty(name="参考贴图尺寸", description="正方形贴图的边长（像素）",
                          default=1024, min=2)

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        vals = []
        for ob in context.selected_objects:
            if ob.type != 'MESH' or not len(ob.data.polygons):
                continue
            _, uv_area, _ = _mesh_uv_data(ob.data)
            w_area = _mesh_world_area(ob)
            if uv_area <= 0 or w_area <= 0:
                continue
            td = math.sqrt(self.ref_size * self.ref_size * uv_area / w_area)
            vals.append(td)
            print("Labor 纹理密度: %s = %.1f px/m" % (ob.name, td))
        if not vals:
            self.report({'WARNING'}, "所选物体没有 UV 或表面积为 0")
            return {'CANCELLED'}
        self.report({'INFO'}, "纹理密度（px/m）平均 %.1f ｜ 最小 %.1f ｜ 最大 %.1f（详情见系统控制台）"
                    % (sum(vals) / len(vals), min(vals), max(vals)))
        return {'FINISHED'}


class LABOR_OT_texel_density_set(bpy.types.Operator):
    """把所选物体的纹理密度统一设置为指定值（各 UV 岛独立绕自身中心缩放，布局不乱）"""
    bl_idname = "labor.texel_density_set"
    bl_label = "设置纹理密度"
    bl_options = {'REGISTER', 'UNDO'}

    target: FloatProperty(name="目标密度 (px/m)", default=512.0, min=0.1, precision=1)
    ref_size: IntProperty(name="参考贴图尺寸", default=1024, min=2)

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        done = skip = 0
        for ob in context.selected_objects:
            if ob.type != 'MESH' or not len(ob.data.polygons):
                continue
            uv, uv_area, islands = _mesh_uv_data(ob.data)
            w_area = _mesh_world_area(ob)
            if uv is None or uv_area <= 0 or w_area <= 0:
                skip += 1
                continue
            current = math.sqrt(self.ref_size * self.ref_size * uv_area / w_area)
            if current <= 1e-9:
                skip += 1
                continue
            factor = self.target / current
            uvs = uv.data
            for loops in islands:
                pts = [uvs[li].uv for li in loops]
                cx = sum(p.x for p in pts) / len(pts)
                cy = sum(p.y for p in pts) / len(pts)
                for li in loops:
                    u = uvs[li].uv
                    uvs[li].uv = (cx + (u.x - cx) * factor, cy + (u.y - cy) * factor)
            done += 1
        self.report({'INFO'}, "已统一纹理密度：成功 %d ｜ 跳过 %d" % (done, skip))
        return {'FINISHED'}


# ================================================================ 快速物理沉降
class LABOR_OT_quick_settle(bpy.types.Operator):
    """用刚体快速结算所选物体的自然堆叠，并烘焙为普通变换（做完自动移除物理）"""
    bl_idname = "labor.quick_settle"
    bl_label = "快速物理沉降 (Settle)"
    bl_options = {'REGISTER', 'UNDO'}

    frames: IntProperty(name="结算帧数", default=40, min=1)
    shape: EnumProperty(
        name="碰撞形状",
        items=(('BOX', "包围盒", "快"), ('CONVEX_HULL', "凸壳", "较准"),
               ('MESH', "网格", "最准最慢")),
        default='BOX',
    )
    mass: FloatProperty(name="质量", default=1.0, min=0.001)
    use_ground: BoolProperty(name="生成地面", description="在指定高度生成临时地面", default=True)
    floor_z: FloatProperty(name="地面高度", default=0.0, precision=4)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        objs = [o for o in context.selected_objects]
        scene = context.scene
        if scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
        ground = None
        if self.use_ground:
            bpy.ops.mesh.primitive_plane_add(size=2000, location=(0, 0, self.floor_z))
            ground = context.active_object
            ground.name = "Labor_TmpGround"
            bpy.ops.rigidbody.object_add()
            ground.rigid_body.type = 'PASSIVE'
        cu.select_only(context, objs)
        for ob in objs:
            try:
                bpy.ops.rigidbody.object_add()
                ob.rigid_body.type = 'ACTIVE'
                ob.rigid_body.shape = self.shape
                ob.rigid_body.mass = self.mass
            except Exception as ex:
                print("Labor 沉降: 跳过 %s (%s)" % (ob.name, ex))
        scene.frame_set(1)
        scene.frame_set(self.frames)
        # 烘焙为普通变换
        cu.select_only(context, objs)
        bpy.ops.object.visual_transform_apply()
        bpy.ops.rigidbody.objects_remove()
        if ground is not None:
            bpy.data.objects.remove(ground, do_unlink=True)
        scene.frame_set(1)
        self.report({'INFO'}, "已沉降并烘焙 %d 个物体" % len(objs))
        return {'FINISHED'}


# ================================================================ 场景清理
class LABOR_OT_scene_cleanup(bpy.types.Operator):
    """场景清理：删除空网格物体 / 合并重复材质（同名 .001）/ 清除未使用数据块"""
    bl_idname = "labor.scene_cleanup"
    bl_label = "场景清理 (Cleanup)"
    bl_options = {'REGISTER', 'UNDO'}

    remove_empty: BoolProperty(name="删除空网格物体", description="没有任何顶点的网格",
                               default=True)
    merge_materials: BoolProperty(name="合并重复材质", description="把 名字.001 式的重名材质"
                                  "的用户全部重定向到基准材质", default=True)
    purge_orphans: BoolProperty(name="清除未使用数据", description="清除所有零用户数据块（含递归）",
                                default=False)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        n_empty = n_mat = 0
        if self.remove_empty:
            empties = [o for o in bpy.data.objects
                       if o.type == 'MESH' and o.data and len(o.data.vertices) == 0]
            for o in empties:
                bpy.data.objects.remove(o, do_unlink=True)
            n_empty = len(empties)
        if self.merge_materials:
            base_map = {}
            for m in list(bpy.data.materials):
                base = re.sub(r'\.\d{3}$', '', m.name)
                keep = base_map.setdefault(base, m)
                if keep is m:
                    continue
                m.user_remap(keep)  # 全部用户重定向到基准材质
                n_mat += 1
        if self.purge_orphans:
            bpy.data.orphans_purge(do_recursive=True)
        self.report({'INFO'}, "清理完成：删除空物体 %d ｜ 合并材质 %d" % (n_empty, n_mat))
        return {'FINISHED'}


# ================================================================ 原点到底部中心
class LABOR_OT_origin_to_bottom(bpy.types.Operator):
    """把所选网格物体的原点移到包围盒底部中心（物体在世界中的位置不变）"""
    bl_idname = "labor.origin_to_bottom"
    bl_label = "原点到底部中心"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            if ob.type != 'MESH' or not ob.data:
                continue
            cu.move_origin_to_bottom(ob)
        return {'FINISHED'}


# ================================================================ 面板
class LABOR_PT_community(bpy.types.Panel):
    bl_label = "社区呼声 · 补缺"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Labor"
    bl_order = 9

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator(LABOR_OT_circular_array.bl_idname, icon='MOD_SCREW')
        col.operator(LABOR_OT_scale_to_size.bl_idname, icon='ARROW_LEFTRIGHT')
        col.separator()
        col.operator(LABOR_OT_select_by_size.bl_idname, icon='ZOOM_SELECTED')
        col.operator(LABOR_OT_select_by_polys.bl_idname, icon='SEQ_CHROMA_SCOPE')
        col.separator()
        col.label(text="纹理密度 (px/m)：", icon='UV_DATA')
        row = col.row(align=True)
        row.operator(LABOR_OT_texel_density_measure.bl_idname, text="测量")
        row.operator(LABOR_OT_texel_density_set.bl_idname, text="统一设置")
        col.separator()
        col.operator(LABOR_OT_quick_settle.bl_idname, icon='PHYSICS')
        col.operator(LABOR_OT_scene_cleanup.bl_idname, icon='BRUSH_DATA')
        col.operator(LABOR_OT_origin_to_bottom.bl_idname, icon='OBJECT_ORIGIN')


CLASSES = (LABOR_OT_circular_array, LABOR_OT_scale_to_size,
           LABOR_OT_select_by_size, LABOR_OT_select_by_polys,
           LABOR_OT_texel_density_measure, LABOR_OT_texel_density_set,
           LABOR_OT_quick_settle, LABOR_OT_scene_cleanup,
           LABOR_OT_origin_to_bottom, LABOR_PT_community)
