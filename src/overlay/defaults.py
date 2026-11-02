import bpy


AREA_TYPE_TO_REGIONS = {

    "VIEW_3D": ["WINDOW", "HEADER", "TOOL_HEADER", "UI", "TOOLS", "ASSET_SHELF", "ASSET_SHELF_HEADER"],
    "IMAGE_EDITOR": ["WINDOW", "HEADER", "TOOL_HEADER", "UI", "TOOLS", "ASSET_SHELF", "ASSET_SHELF_HEADER"],
    "NODE_EDITOR": ["WINDOW", "HEADER", "UI", "TOOLS", "ASSET_SHELF", "ASSET_SHELF_HEADER"],
    "SEQUENCE_EDITOR": ["WINDOW", "HEADER", "FOOTER", "PREVIEW", "CHANNELS", "TOOL_HEADER", "TOOLS", "UI"],
    "CLIP_EDITOR": ["WINDOW", "HEADER", "PREVIEW", "UI", "TOOLS", "CHANNELS"],
    "DOPESHEET_EDITOR": ["WINDOW", "HEADER", "FOOTER", "CHANNELS", "UI"],
    "GRAPH_EDITOR": ["WINDOW", "HEADER", "FOOTER", "CHANNELS", "UI"],
    "NLA_EDITOR": ["WINDOW", "HEADER", "FOOTER", "CHANNELS", "UI"],
    "TEXT_EDITOR": ["WINDOW", "HEADER", "UI", "FOOTER"],
    "CONSOLE": ["WINDOW", "HEADER"],
    "INFO": ["WINDOW", "HEADER"],
    "OUTLINER": ["WINDOW", "HEADER"],
    "PROPERTIES": ["WINDOW", "HEADER", "NAVIGATION_BAR"],

    "FILE_BROWSER": ["WINDOW", "HEADER", "UI", "TOOLS", "TOOL_PROPS"],
    "SPREADSHEET": ["WINDOW", "HEADER", "FOOTER", "UI", "TOOLS"],

    "PREFERENCES": ["WINDOW", "HEADER", "UI"],
}

AREA_TYPES_TO_SPACE = {
    "VIEW_3D": bpy.types.SpaceView3D,
    "IMAGE_EDITOR": bpy.types.SpaceImageEditor,
    "NODE_EDITOR": bpy.types.SpaceNodeEditor,
    "SEQUENCE_EDITOR": bpy.types.SpaceSequenceEditor,
    "CLIP_EDITOR": bpy.types.SpaceClipEditor,
    "DOPESHEET_EDITOR": bpy.types.SpaceDopeSheetEditor,
    "GRAPH_EDITOR": bpy.types.SpaceGraphEditor,
    "NLA_EDITOR": bpy.types.SpaceNLA,
    "TEXT_EDITOR": bpy.types.SpaceTextEditor,
    "CONSOLE": bpy.types.SpaceConsole,
    "INFO": bpy.types.SpaceInfo,
    "OUTLINER": bpy.types.SpaceOutliner,
    "PROPERTIES": bpy.types.SpaceProperties,
    "FILE_BROWSER": bpy.types.SpaceFileBrowser,
    "SPREADSHEET": bpy.types.SpaceSpreadsheet,
    "PREFERENCES": bpy.types.SpacePreferences,
}
