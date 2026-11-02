import typing as tp
import bpy
import sys
import textwrap
from datetime import datetime
from .. import utils
from . import tiny
from .. import registry as rg
from .. import types
from ..overseer import is_debug_mode
from ..api import diagnostics
from ..api import snapshot
from ..ribbon import audio
from ..ribbon.summons import confirm




def button(layout: bpy.types.UILayout, action: tiny.ActionType, text: str, icon="NONE", emboss=True, **props):
    op = layout.operator("exciton.action", text=text, icon=tp.cast(tp.Any, icon), emboss=emboss)
    for key, value in {"type": action, **props}.items():
        setattr(op, key, value)
    return op


def checkbox_icon(checked: tp.Any) -> str:
    return "CHECKBOX_HLT" if checked else "CHECKBOX_DEHLT"


def warning(layout: bpy.types.UILayout, header: str, detail="", icon="ERROR"):
    box = layout.box()
    box.alert = True
    box.label(text=header, icon=tp.cast(tp.Any, icon))
    if detail:
        wrapped_text(box, detail)
    return box




def version(layout: bpy.types.UILayout):
    row = layout.row()
    text = row.row()
    text.active = False
    text.label(text=f"Exciton v{utils.version_label()}")
    button(row, "COPY_VERSION", "", icon="COPYDOWN", emboss=False)


def loading(layout: bpy.types.UILayout):
    box = layout.box()
    box.alert = True
    box.label(text="Loading...", icon="SORTTIME")


def checkbox(layout: bpy.types.UILayout, data: types.Config, target_key, label=""):
    button(layout, "TOGGLE_KEY", label, icon=checkbox_icon(data.get(target_key)), target_key=target_key)


def snapshot_icon(data: types.Config):
    if data.get("_snapshot_loading"):
        return "SORTTIME"
    elif utils.was_recent(data.get("_snapshot_loading_latest"), snapshot.RATE_LIMIT_SECONDS):
        return "ERROR"
    return "FILE_REFRESH"


def testing_utils(layout: bpy.types.UILayout, data: types.Config):
    if not utils.IS_DEV:
        return

    header, panel = layout.panel("testing_utils", default_closed=True)
    header.label(text="Testing Utilities")

    if not panel:
        layout.separator(type="LINE")
        return

    button(panel, "REDRAW", "Redraw")
    button(panel, "TOGGLE_CHANNEL", "Channel", icon=checkbox_icon(rg.Channel.is_open()))
    button(panel, "DELETE_CONFIG_KEY", "Delete snapshot", target_key="_active_snapshot")
    button(panel, "SNAPSHOT_RL", "Snapshot RL")

    row = panel.row()
    checkbox(row, data, "_test_force_snapshot_401", "Snapshot 401")
    checkbox(row, data, "_test_force_snapshot_500", "Snapshot 500")

    mock_script(panel, data)
    mock_command_script(panel)
    layout.separator(type="LINE")



def mock_script(layout: bpy.types.UILayout, data: types.Config):
    header, panel = layout.panel("testing_script_confirm", default_closed=True)
    header.label(text="Script confirmation")
    if not panel:
        return
    ticked = data.get("_test_script_permissions") or []
    col = panel.column(align=True)

    for permission, name in confirm.SHORT_NAMES.items():
        if permission == "SEE_SCREEN":
            continue
        button(
            col,
            "TOGGLE_TEST_PERMISSION",
            name.capitalize(),
            icon=checkbox_icon(permission in ticked),
            emboss=False,
            target_key=permission,
        )
    button(panel, "MOCK_SCRIPT", f"Mock script ({tiny.MOCK_SCRIPT_DELAY_SECONDS}s)")
    button(panel, "MOCK_SCREENSHOT", f"Mock screenshot ({tiny.MOCK_SCRIPT_DELAY_SECONDS}s)")
    button(panel, "CLEAR_SCRIPT_ALLOWS", "Clear permissions")




def mock_command_script(layout: bpy.types.UILayout):
    header, panel = layout.panel("testing_command_script_confirm", default_closed=True)
    header.label(text="Command confirmation")
    if not panel:
        return
    col = panel.column(align=True)
    for verdict, (text, _, icon) in confirm.VERDICTS.items():
        button(col, "MOCK_COMMAND_SCRIPT", text.split(":")[0], icon=icon, target_key=verdict)
    button(col, "MOCK_ADDON_OPERATOR", "Add-on operator", icon="PLUGIN")
    note = panel.row()
    note.active = False
    note.label(text=f"Asks after {tiny.MOCK_SCRIPT_DELAY_SECONDS}s")


def debugging(layout: bpy.types.UILayout, data: types.Config):
    if not is_debug_mode(data):
        return

    header, panel = layout.panel("debugging", default_closed=True)
    header.label(text="Debugging")

    if not panel:
        layout.separator(type="LINE")
        return

    button(panel, "RELOAD_SETTINGS", "Reload settings", icon="SORTTIME" if data.get("_snapshot_loading") else "FILE_REFRESH")
    button(panel, "OPEN_LOGS", "Open logs", icon="FILE_FOLDER")
    status = data.get("_diagnostics") or {}
    just_sent = status.get("state") == "SENT" and utils.was_recent(status.get("sent_at"), diagnostics.SENT_FEEDBACK_SECONDS)
    send = panel.row()
    send.enabled = diagnostics.can_send(data)
    button(send, "SEND_DIAGNOSTICS", "Sent" if just_sent else "Send diagnostics", icon="CHECKMARK" if just_sent else "EXPORT")

    if status:
        match status.get("state"):
            case "SENDING":
                panel.label(text="Sending…", icon="SORTTIME")
            case "FAILED":
                box = panel.box()
                box.alert = True
                box.label(text=f"Not sent: {status.get('error')}", icon="ERROR")
    layout.separator(type="LINE")


def logged_in(layout: bpy.types.UILayout, data: types.Config):
    row = layout.row()
    button(row, "SIGN_OUT", "Sign out")
    button(row, "OPEN_SETTINGS", "Settings")

    voice_setup(layout, data)
    scripts(layout, data)
    update_required(layout, data)




def scripts(layout: bpy.types.UILayout, data: types.Config):
    allowed = confirm.allowed_now()
    commands = confirm.approved_count()
    if not data.get("_active_snapshot") or not (allowed or commands):
        return
    header, panel = layout.panel("script_permissions", default_closed=True)
    header.label(text="Don't ask for")
    if panel:
        col = panel.column(align=True)
        col.active = False
        for permission, name in confirm.SHORT_NAMES.items():
            if permission in allowed:
                col.label(text=f"{name.capitalize()}, {_until(allowed[permission])}")
        if commands:
            col.label(text=f"{commands} script command{'' if commands == 1 else 's'} allowed here")
        button(panel, "CLEAR_SCRIPT_ALLOWS", "Clear permissions")
    layout.separator(type="LINE")


def _until(expires: float | None) -> str:
    if expires is None:
        return "until Blender closes"
    when = datetime.fromtimestamp(expires)
    return f"until {when:%b} {when.day}"



def voice_setup(layout: bpy.types.UILayout, data: types.Config):
    if not data.get("_active_snapshot"):
        layout.separator(type="LINE")
        box = warning(layout, "Snapshot error", "Couldn't download latest snapshot. Press to retry or come back later.")
        row = box.row()
        row.alignment = "CENTER"
        button(row, "SNAPSHOT_RL", "Try again", icon=snapshot_icon(data))
        return

    layout.separator(type="LINE")

    force = utils.FORCE_NO_PORTAUDIO
    if not audio.portaudio_available() or force:
        portaudio_missing(layout, linux=force == "linux" if force else sys.platform.startswith("linux"))
        layout.separator(type="LINE")
        return

    row = layout.row()
    split = row.split(align=False, factor=0.1)
    split.label(text="Mic")
    split = split.split(factor=0.8)
    split.menu("EXCITON_MT_mic_menu", text=tiny.selected_mic_label())
    button(split, "RELOAD_DEVICES", "", icon="FILE_REFRESH")

    row = layout.row()
    row.alignment = "CENTER"
    button(row, "TOGGLE_PRIME_MIC", "Keep mic warm (Faster)", icon=checkbox_icon(data.get("prime_mic")), emboss=False)

    layout.separator(type="LINE")



def update_required(layout: bpy.types.UILayout, data: types.Config):
    required = data.get("_update_required")
    if utils.FORCE_UPDATE_REQUIRED:

        needed = f"version 99.0.0 or later is needed (you have {utils.EXTENSION_VERSION})"
        required = {"message": f"Update the Exciton add-on to keep using it: {needed}."}
    if required:
        layout.separator()
        warning(layout, "Update required", required.get("message") or "Update the Exciton add-on to keep using it.")



def portaudio_missing(layout: bpy.types.UILayout, linux: bool):
    if not linux:

        warning(
            layout,
            "Microphone unavailable",
            f"PortAudio couldn't load ({audio.portaudio_error or 'library not found'}). Reinstall the add-on, then restart Blender.",
        )
        return

    box = warning(
        layout, "Install PortAudio", "Voice input needs PortAudio for the microphone. Install it, then restart Blender."
    )
    box.separator()
    box.label(text="Ubuntu or Debian:")
    box.label(text=tiny.PORTAUDIO_INSTALL_COMMAND)
    box.label(text="Other distros: the portaudio package.")
    row = box.row()
    row.alignment = "CENTER"
    button(row, "COPY_PORTAUDIO_COMMAND", "Copy command", icon="COPYDOWN")


def wrapped_text(layout: bpy.types.UILayout, text: str, max_chars=40):
    col = layout.column(align=True)
    for line in textwrap.wrap(text, width=max_chars):
        col.label(text=line)
