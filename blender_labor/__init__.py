# -*- coding: utf-8 -*-
"""Blender Labor — 场景装配工具集（Blender 版）
移植自 3ds Max 插件 AssemblyTool，仅保留 Blender 未原生提供的功能。
入口：3D 视口右侧 N 面板 → 「Labor」分类。
"""

bl_info = {
    "name": "Blender Labor（Labor 场景装配工具集）",
    "author": "Ported from AssemblyTool (Andrew Averkin, Viacheslav Sutormin)",
    "version": (1, 2, 0),
    "blender": (3, 6, 0),
    "location": "3D 视口 > N 面板 > Labor",
    "description": "面向场景装配工作流的效率工具集：下落、表面放置、散布、绘制、随机化、替换、自动成组、网格排布/打包、批量导入导出、批量标准化、资产体检、纹理密度、物理沉降等",
    "doc_url": "",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty

from . import ops_transform, ops_scatter, ops_painter, ops_randomize
from . import ops_array, ops_group, ops_pack, ops_io, ops_material, ops_community, ops_assets

_modules = (ops_transform, ops_scatter, ops_painter, ops_randomize,
            ops_array, ops_group, ops_pack, ops_io, ops_material, ops_community, ops_assets)

_classes = []
for _m in _modules:
    _classes.extend(_m.CLASSES)


def register():
    for cls in _classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            # 重复加载（如 F3 Reload Scripts）时先注销再注册
            try:
                bpy.utils.unregister_class(cls)
                bpy.utils.register_class(cls)
            except Exception as ex:
                print("Labor 注册失败: %s (%s)" % (cls.__name__, ex))
                raise
    bpy.types.Scene.labor_painter = PointerProperty(type=ops_painter.LABOR_PainterSettings)


def unregister():
    del bpy.types.Scene.labor_painter
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
