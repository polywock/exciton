import sys
import typing as tp
import bpy
from .. import utils
from .. import configs
from .. import types
from .. import registry as rg
from .. import windows
from ..commands import context as command_context













CANCEL_EVENTS = {"ESC", "X", "DEL", "BACK_SPACE"}
SUBMIT_EVENTS = {"NUMPAD_ENTER", "RET"}

CONTROL_KEYS = CANCEL_EVENTS | SUBMIT_EVENTS | {"LEFT_ARROW", "RIGHT_ARROW", "UP_ARROW", "DOWN_ARROW", "SPACE"}

NO_CAPTION = "No caption to show"

CAPTION_KEYS_GUIDE = [
    "Left / Right: Navigate",
    "Enter: Resume captions",
    "Up / Down: Reading speed",
    "Esc, X, Del: Clear",
]

LIVE_HINT_SECONDS = 4.0
MODIFIERS = ("shift", "ctrl", "alt", "oskey")
WATCHDOG_INTERVAL = 2.0
MAX_REPAIRS = 3


class KeymapId(tp.NamedTuple):
    name: str
    space_type: str
    region_type: str


WINDOW_KEYMAP = KeymapId("Window", "EMPTY", "WINDOW")


Slot: tp.TypeAlias = tuple[KeymapId, int]


class _State:
    generation: str = ""
    expected: tp.ClassVar[set[Slot]] = set()
    repairs: int = 0


_watchdog: types.TimerCallback | None = None


class EXCITON_OT_shortcut(bpy.types.Operator):
    bl_idname = "exciton.shortcut"
    bl_label = "Voice Control (Auto-managed, do not touch please)"


    runtime_uuid: bpy.props.StringProperty(default="", options={"HIDDEN"})
    index: bpy.props.IntProperty(options={"HIDDEN"})

    start_type: str | None = None
    control_mode: bool = False

    chat_space_held: bool = False

    pressed_in: command_context.CommandContext | None = None

    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> set[tp.Literal["FINISHED", "CANCELLED", "RUNNING_MODAL", "PASS_THROUGH", "INTERFACE"]]:
        self.start_type = None
        if not _State.generation or self.runtime_uuid != _State.generation:
            return {"PASS_THROUGH"}

        data = configs.get_config()
        shortcut = utils.list_get(get_shortcuts(data), self.index)
        if not (shortcut and event_matches_fullkey(event, shortcut.get("trigger"))):
            return {"PASS_THROUGH"}

        windows.remember(context.window)


        if shortcut.get("action") == "CHAT" and rg.Ribbon.live_chat_enabled():
            said = _toggle_live(command_context.capture())
            if said:
                rg.Overlay.center.show(*said, area=_area_rect(context))
            return {"FINISHED"}

        self.start_type = event.type

        bpy.context.window_manager.modal_handler_add(self)

        if shortcut.get("action") == "CONTROL":
            self.control_mode = True
            self.pressed_in = command_context.capture()
            rg.Overlay.center.show_guide(_control_guide(rg.Ribbon.has_jobs(), rg.Ribbon.live_chat_enabled()), _area_rect(context))
        elif shortcut.get("action") == "COMMAND" or shortcut.get("action") == "CHAT":
            action = tp.cast(types.ChatOrCommand, shortcut.get("action"))


            rg.Ribbon.start(action, command_context.capture())
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        start_type = self.start_type
        if not start_type:
            self.cancel_common()
            return {"CANCELLED"}


        if self.chat_space_held and event.type == "SPACE":
            if event.value == "RELEASE":
                self.chat_space_held = False
            return {"RUNNING_MODAL"}



        if event.type == start_type and event.value == "RELEASE":
            return self._finish()
        if event.type == start_type and event.value == "PRESS":
            return {"RUNNING_MODAL"}



        if self.control_mode and event.type in CONTROL_KEYS:
            if event.value == "PRESS":
                self._control(event.type)
            return {"RUNNING_MODAL"}

        if event.type in CANCEL_EVENTS and event.value == "PRESS":
            self.cancel_common()
            return {"CANCELLED"}


        if not self.control_mode and event.type == "SPACE" and event.value == "PRESS":
            try:
                bpy.ops.wm.call_menu("INVOKE_DEFAULT", name="SCREEN_MT_user_menu")
            except Exception:
                pass
            self.cancel_common()
            return {"CANCELLED"}

        if event.type in SUBMIT_EVENTS and event.value == "PRESS":
            return self._finish()

        return {"PASS_THROUGH"}

    def _finish(self) -> set[tp.Literal["FINISHED"]]:
        if self.control_mode:
            rg.Overlay.center.hide_guide()
        else:
            rg.Ribbon.stop()
        return {"FINISHED"}



    def _control(self, key: str):
        if key in ("LEFT_ARROW", "RIGHT_ARROW"):
            if rg.Ribbon.replay(-1 if key == "LEFT_ARROW" else 1):
                rg.Overlay.center.hide_guide()
            else:
                rg.Overlay.center.flash(NO_CAPTION)
        elif key in SUBMIT_EVENTS:

            rg.Overlay.center.flash("Resuming" if rg.Ribbon.move_on() else NO_CAPTION)
        elif key == "SPACE":
            self._start_chat()
        elif key in ("UP_ARROW", "DOWN_ARROW"):
            speed = rg.Overlay.speed.change(1 if key == "UP_ARROW" else -1)
            rg.Overlay.center.flash(f"Reading speed {speed:g}×")
        else:

            rg.Ribbon.dismiss()
            rg.Overlay.center.flash("Cleared")




    def _start_chat(self):
        rg.Overlay.center.hide_guide()
        self.control_mode = False
        self.chat_space_held = True
        if rg.Ribbon.live_chat_enabled():


            said = _toggle_live(self.pressed_in)
            if said:
                rg.Overlay.center.flash(*said)
            return
        rg.Ribbon.start("CHAT", self.pressed_in)

    def cancel_common(self):
        if self.control_mode:
            rg.Overlay.center.hide_guide()
        else:
            rg.Ribbon.cancel()

    def cancel(self, context):
        self.cancel_common()
        utils.logger.debug("Shortcut modal was cancelled by Blender")


OPERATOR = EXCITON_OT_shortcut.bl_idname

classes = (EXCITON_OT_shortcut,)


def register():
    utils.register(classes)


def unregister():
    utils.unregister(classes)


def clear_keymaps_for_launch(cb: types.AnyFunction):
    tried = 0

    def delayed_sync():
        nonlocal tried
        tried += 1
        if tried > 10:
            utils.logger.warning("Keyconfigs never became ready, shortcuts not set up")
            return None
        user = bpy.context.window_manager.keyconfigs.user
        addon = bpy.context.window_manager.keyconfigs.addon
        if not (addon and user and user.keymaps.get("Window")):
            return 0.5

        sync_keymaps(True)
        cb()

        return None

    utils.register_timer(delayed_sync, first_interval=0.5)


def sync_keymaps(for_launch: bool):
    _State.repairs = 0
    _sync(for_launch)


def _sync(for_launch: bool):
    clear_keymaps()


    if for_launch:
        return

    data = configs.get_config()
    snapshot = data.get("_active_snapshot")
    if not snapshot:
        return

    kcs = bpy.context.window_manager.keyconfigs
    if not (kcs.addon and kcs.user):
        return

    triggers = _active_triggers(data)
    _, targets = _scan_user_keymaps(kcs.user, triggers)

    generation = utils.random_id()
    for km_id, index in targets:
        km = kcs.addon.keymaps.new(name=km_id.name, space_type=km_id.space_type, region_type=km_id.region_type)
        create_shortcut(km, triggers[index], index, generation)


    kcs.update()

    _State.generation = generation
    _State.expected = targets
    utils.logger.info("Synced %d shortcut(s) into %d keymap slot(s)", len(triggers), len(targets))
    if targets:
        _ensure_watchdog()
    return True


def create_shortcut(km: bpy.types.KeyMap, full_key: types.FullKey, index: int, generation: str):
    kmi = km.keymap_items.new(
        OPERATOR,
        value="PRESS",
        type=(tp.cast(tp.Any, full_key.get("type"))),
        shift=int(full_key.get("shift", 0)),
        ctrl=int(full_key.get("ctrl", 0)),
        alt=int(full_key.get("alt", 0)),
        oskey=int(full_key.get("oskey", 0)),
    )
    tp.cast(tp.Any, kmi.properties).runtime_uuid = generation
    tp.cast(tp.Any, kmi.properties).index = index


def clear_keymaps():
    _State.generation = ""
    _State.expected = set()

    kcs = bpy.context.window_manager.keyconfigs
    if kcs.addon:
        for km in kcs.addon.keymaps:
            _delete_kmi_by_operator(km, OPERATOR)


    kcs.update()


def _active_triggers(data: types.Config) -> dict[int, types.FullKey]:
    shortcuts = get_shortcuts(data)
    return {
        index: shortcut["trigger"]
        for index, shortcut in enumerate(shortcuts)
        if not shortcut.get("disabled") and (shortcut.get("trigger") or {}).get("type")
    }




def _scan_user_keymaps(
    user_kc: bpy.types.KeyConfig, triggers: dict[int, types.FullKey]
) -> tuple[list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]], set[Slot]]:
    ours: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []
    targets: set[Slot] = {(WINDOW_KEYMAP, index) for index in triggers}

    for km in user_kc.keymaps:
        if km.is_modal:
            continue
        km_id = KeymapId(km.name, km.space_type, km.region_type)
        for kmi in km.keymap_items:
            if kmi.idname == OPERATOR:
                ours.append((km, kmi))
                continue
            for index, trigger in triggers.items():
                if _is_conflict(kmi, trigger):
                    targets.add((km_id, index))

    return ours, targets


def _is_conflict(kmi: bpy.types.KeyMapItem, trigger: types.FullKey):
    return (
        kmi.active
        and kmi.type == trigger.get("type")
        and kmi.key_modifier == "NONE"
        and all(kmi_modifier_matches(getattr(kmi, mod), bool(trigger.get(mod))) for mod in MODIFIERS)
        and getattr(kmi, "hyper", 0) in (-1, 0)
    )


def kmi_modifier_matches(value: int, wanted: bool):
    return value == -1 or bool(value) == wanted


def _ensure_watchdog():
    global _watchdog
    if _watchdog and bpy.app.timers.is_registered(_watchdog):
        return
    _watchdog = utils.register_timer(_watchdog_tick, first_interval=WATCHDOG_INTERVAL)


def _watchdog_tick():
    global _watchdog
    if _State.expected:
        try:
            _repair_drift()
        except Exception:
            utils.logger.exception("Shortcut watchdog failed")

    if not _State.expected:
        _watchdog = None
        return None
    return WATCHDOG_INTERVAL


def _repair_drift():
    kcs = bpy.context.window_manager.keyconfigs
    if not kcs.user:
        return

    kcs.update()
    reason, strays = _find_drift(kcs.user)
    if not reason:
        _State.repairs = 0
        return

    _State.repairs += 1
    if _State.repairs > MAX_REPAIRS:
        if _State.repairs == MAX_REPAIRS + 1:
            utils.logger.warning("Shortcuts keep drifting, giving up until next sync: %s", reason)
        return

    utils.logger.info("Shortcuts drifted, re-syncing: %s", reason)

    for km, kmi in strays:
        km.keymap_items.remove(kmi)
    _sync(False)


    if not _find_drift(kcs.user)[0]:
        _State.repairs = 0


def _find_drift(user_kc: bpy.types.KeyConfig):
    triggers = _active_triggers(configs.get_config())
    ours, targets = _scan_user_keymaps(user_kc, triggers)

    strays: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []
    found: dict[Slot, list[bpy.types.KeyMapItem]] = {}
    for km, kmi in ours:
        props = tp.cast(tp.Any, kmi.properties)
        slot = (KeymapId(km.name, km.space_type, km.region_type), props.index)
        if props.runtime_uuid != _State.generation or slot not in _State.expected:
            strays.append((km, kmi))
        else:
            found.setdefault(slot, []).append(kmi)

    reason = None
    if strays:
        reason = f"{len(strays)} foreign item(s)"
    elif targets != _State.expected:
        reason = "conflicting shortcuts changed"
    else:
        for slot in _State.expected:
            items = found.get(slot, [])
            if len(items) != 1:
                reason = f"{len(items)} item(s) in {slot[0].name} for shortcut {slot[1]}"
            elif items[0].is_user_modified or not items[0].active:
                reason = f"user modified item in {slot[0].name} for shortcut {slot[1]}"
            if reason:
                break

    return reason, strays


def _delete_kmi_by_operator(km: bpy.types.KeyMap, op: str):
    while True:
        kmi = km.keymap_items.find_from_operator(op)
        if not kmi:
            break
        km.keymap_items.remove(kmi)



def _control_guide(has_jobs: bool, live: bool) -> str:
    if live:
        space = "Space: Tap to start or end live chat"
    elif has_jobs:
        space = "Space: Tap once to start listening"
    else:
        space = "Space: Tap once to start a chat"
    return "\n".join([*(CAPTION_KEYS_GUIDE if has_jobs else []), space])




def _toggle_live(context: command_context.CommandContext | None) -> tuple[str, float] | None:
    match rg.Ribbon.toggle_live(context):
        case "started":
            chat = next((s for s in get_shortcuts(configs.get_config()) if s.get("action") == "CHAT"), None)
            key = shortcut_label(chat.get("trigger")) if chat else ""
            text = f"Tap {key} again to end live chat" if key else "Tap the chat shortcut again to end live chat"
            return text, LIVE_HINT_SECONDS
        case "ended":
            return "Live chat ended", rg.Overlay.center.FLASH_SECONDS
    return None



def _area_rect(context: bpy.types.Context) -> types.FloatRect | None:
    area = getattr(context, "area", None)
    return (area.x, area.y, area.width, area.height) if area else None



def shortcut_label(full_key: types.FullKey | None) -> str:
    key = (full_key or {}).get("type")
    if not key:
        return ""
    try:
        name = bpy.types.Event.bl_rna.properties["type"].enum_items[key].name
    except (KeyError, AttributeError):
        name = key.replace("_", " ").title()
    os_key = "Cmd" if sys.platform == "darwin" else "Win"
    labels = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "oskey": os_key}
    modifiers = [labels[m] for m in ("ctrl", "alt", "shift", "oskey") if (full_key or {}).get(m)]
    return "+".join([*modifiers, name])


def event_matches_fullkey(event: bpy.types.Event, full_key: types.FullKey):
    if not full_key or not event:
        return False
    return full_key.get("type") == event.type and all(bool(full_key.get(mod)) == getattr(event, mod) for mod in MODIFIERS)


def get_shortcuts(data: types.Config):
    return tp.cast(tp.List[types.Shortcut], (data.get("_active_snapshot") or {}).get("shortcuts") or [])
