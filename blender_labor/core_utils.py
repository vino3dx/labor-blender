# -*- coding: utf-8 -*-
"""blender_labor.core_utils — 通用辅助函数（包围盒 / 射线检测 / 选择 / 复制）"""

import bpy
import random
from mathutils import Vector, Matrix


def world_bbox(obj):
    """返回物体世界空间包围盒 (min Vector, max Vector)，包含修改器评估结果。"""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ob = obj.evaluated_get(depsgraph)
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def children_recursive(obj):
    """递归收集所有子级。"""
    result = []
    stack = list(obj.children)
    while stack:
        o = stack.pop()
        result.append(o)
        stack.extend(o.children)
    return result


def scene_ray(context, origin, direction, exclude=()):
    """场景射线检测（可排除物体），返回 (hit, location, normal, object)。"""
    depsgraph = context.evaluated_depsgraph_get()
    o = Vector(origin)
    d = Vector(direction)
    if d.length == 0:
        return False, None, None, None
    d.normalize()
    hit, loc, normal, idx, obj, matrix = context.scene.ray_cast(depsgraph, o, d)
    if exclude:
        excluded = set(exclude)
        guard = 0
        while hit and obj in excluded and guard < 200:
            o = Vector(loc) + d * 0.001
            hit, loc, normal, idx, obj, matrix = context.scene.ray_cast(depsgraph, o, d)
            guard += 1
    return hit, (Vector(loc) if hit else None), (Vector(normal) if hit else None), obj


def translate_world(ob, vec):
    """沿世界坐标轴平移物体（保持旋转/缩放）。"""
    ob.matrix_world = Matrix.Translation(Vector(vec)) @ ob.matrix_world


def select_only(context, objs):
    """只选中给定物体（并设活动物体）。"""
    for o in context.selected_objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass
    for o in objs:
        try:
            o.select_set(True)
        except RuntimeError:
            pass
    if objs:
        context.view_layer.objects.active = objs[0]


def make_single_user_data(ob):
    """把物体网格数据转为单一用户（join 前保险）。"""
    if ob.data and ob.data.users > 1:
        ob.data = ob.data.copy()


def linked_duplicate(context, obj, name=None):
    """创建关联复制（共享网格数据，省内存）。"""
    new = obj.copy()
    if name:
        new.name = name
    context.collection.objects.link(new)
    return new


def delete_objects(context, objs):
    """删除物体（保持上下文安全）。"""
    objs = list(objs)
    if not objs:
        return
    with context.temp_override(active_object=objs[0],
                               selected_objects=objs,
                               selected_editable_objects=objs):
        bpy.ops.object.delete()


def random_surface_point(obj):
    """在物体网格表面随机取一点，返回 (世界坐标点, 世界法线)；失败返回 (None, None)。"""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ob = obj.evaluated_get(depsgraph)
    try:
        mesh = ob.to_mesh()
    except Exception:
        return None, None
    polys = mesh.polygons
    if not len(polys):
        ob.to_mesh_clear()
        return None, None
    total = sum(p.area for p in polys)
    if total <= 0:
        ob.to_mesh_clear()
        return None, None
    r = random.uniform(0, total)
    acc = 0.0
    pt, nrm = None, None
    mw = ob.matrix_world
    try:
        nmat = mw.to_3x3().inverted_safe().transposed()  # 法线变换矩阵
    except Exception:
        nmat = mw.to_3x3()
    for p in polys:
        acc += p.area
        if r <= acc:
            vs = [mw @ mesh.vertices[vi].co for vi in p.vertices[:3]]
            u = random.random()
            v = random.random()
            if u + v > 1.0:
                u, v = 1.0 - u, 1.0 - v
            pt = vs[0] * (1 - u - v) + vs[1] * u + vs[2] * v
            nrm = (nmat @ p.normal).normalized()
            break
    ob.to_mesh_clear()
    return pt, nrm


def bbox_gap(mn1, mx1, mn2, mx2):
    """两个包围盒之间的间隙距离（相交时为 0）。"""
    gap = 0.0
    for i in range(3):
        g = max(mn1[i], mn2[i]) - min(mx1[i], mx2[i])
        if g > 0:
            gap += g * g
    return gap ** 0.5


def move_origin_to_bottom(ob):
    """把网格物体原点移到包围盒底部中心（物体在世界中的位置不变）。"""
    mn, mx = world_bbox(ob)
    P = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
    d = ob.matrix_world.inverted() @ P
    ob.data.transform(Matrix.Translation(-d))
    ob.matrix_world = ob.matrix_world @ Matrix.Translation(d)
