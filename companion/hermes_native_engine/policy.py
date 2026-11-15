"""Generic finite admission and service schemas; no household grants."""
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator


def action_fields(limits):
    return {k: ({'type': 'number', 'minimum': v[0], 'maximum': v[1]} if isinstance(v, tuple) else v) for k, v in limits.items()}


def public_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError('public HTTP(S) URL required')
    import ipaddress, socket
    try: addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except OSError as exc: raise ValueError('unresolved public URL') from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError('private/internal URL')
    return url

SOURCE = "homeassistant-native"
MODEL = "gpt-realtime-2.1"
ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]+\Z")
READ_DOMAINS = {"light", "fan", "climate", "media_player", "sensor", "binary_sensor", "weather", "sun", "switch", "cover", "humidifier", "vacuum", "select"}
# Grant only exact actions below; switches/covers/vacuums require explicit review.
ACTIONS = {
    "light": {"turn_on": {"brightness_pct": (0, 100), "color_temp_kelvin": (2000, 6500)}, "turn_off": {}},
    "switch": {"turn_on": {}, "turn_off": {}},
    "fan": {"turn_on": {}, "turn_off": {}, "set_percentage": {"percentage": (0, 100)}},
    "climate": {"set_temperature": {"temperature": (15, 28)}, "set_hvac_mode": {"hvac_mode": {"type":"string"}}, "set_fan_mode": {"fan_mode": {"type":"string"}}, "set_preset_mode": {"preset_mode": {"type":"string"}}, "set_humidity": {"humidity": (20,45)}},
    "media_player": {"turn_on": {}, "turn_off": {}, "media_play": {}, "media_pause": {}, "media_stop": {}, "media_next_track": {}, "media_previous_track": {}, "volume_set": {"volume_level": (0, 0.65)}, "volume_mute": {"is_volume_muted": {"type":"boolean"}}, "select_source": {"source": {"type":"string","minLength":1,"maxLength":200}}},
    "select": {"select_option": {"option": {"type":"string","minLength":1,"maxLength":128}}},
    "cover": {"open_cover": {}, "close_cover": {}, "stop_cover": {}},
    "humidifier": {"turn_on": {}, "turn_off": {}, "set_humidity": {"humidity": (30, 55)}},
    "vacuum": {"start": {}, "pause": {}, "return_to_base": {}},
}
ATTRS = {"friendly_name", "unit_of_measurement", "device_class", "brightness", "color_temp_kelvin", "percentage", "temperature", "current_temperature", "humidity", "current_humidity", "hvac_action", "hvac_modes", "volume_level", "is_volume_muted", "media_title", "media_artist", "media_album_name", "current_position", "supported_features", "wind_speed", "wind_bearing", "pressure", "cloud_coverage", "apparent_temperature", "dew_point", "forecast", "attribution", "sunrise", "sunset", "source", "source_list", "fan_mode", "fan_modes", "preset_mode", "preset_modes", "min_temp", "max_temp", "target_temp_step", "temperature_unit", "pressure_unit", "wind_speed_unit"}
MEMORY_READ = {"mnemosyne_recall", "mnemosyne_get"}
MEMORY_EFFECT = {"mnemosyne_remember", "mnemosyne_update", "mnemosyne_invalidate", "mnemosyne_forget"}
MEMORY_NAMES = MEMORY_READ | MEMORY_EFFECT
MUSIC_READ = {"library_search_tracks", "library_search_albums", "library_search_artists",
              "library_list_library_playlists", "library_list_library_radio", "library_get_album_tracks",
              "library_get_artist_albums", "library_get_playlist_by_uri", "players_list_players",
              "players_get_player", "queue_get_active_queue"}
MUSIC_EFFECT = {"playback_play_media", "playback_pause", "playback_resume", "playback_stop",
                "playback_next_track", "playback_previous_track", "volume_volume_set"}


def music_wire(name):
    from tools.mcp_tool_schema import mcp_prefixed_tool_name
    return mcp_prefixed_tool_name("Music Assistant", name)


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def schema(name, description, properties, required=()):
    return {"type": "function", "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(required), "additionalProperties": False}}


def exact(obj, required, optional=()):
    if type(obj) is not dict or not set(required) <= set(obj) or set(obj) - set(required) - set(optional):
        raise ValueError("unexpected fields")


def plain(value, limit=4000):
    if type(value) is not str or not 1 <= len(value) <= limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("text")
    return value


def project_state(row):
    if type(row) is not dict or "error" in row:
        raise ValueError("state unavailable")
    return {"entity_id": row["entity_id"], "state": str(row["state"])[:300],
            "attributes": {k: v for k, v in row.get("attributes", {}).items() if k in ATTRS}}


class Policy:
    """Versioned exact-target policy. Never trust a model-provided area or service."""
    def __init__(self, data, *, reviewed_switches=(), select_options=None):
        select_options = {} if select_options is None else select_options
        if type(select_options) is not dict or any(not ENTITY.fullmatch(e) or not e.startswith('select.') or
                type(options) is not list or not options or len(options) > 64 or
                any(type(o) is not str or not 1 <= len(o) <= 128 for o in options) or len(set(options)) != len(options)
                for e, options in select_options.items()):
            raise ValueError('finite reviewed select options required')
        reviewed_switches = frozenset(reviewed_switches)
        if any(not ENTITY.fullmatch(e) or not e.startswith("switch.") for e in reviewed_switches):
            raise ValueError("explicit reviewed switch targets required")
        exact(data, ("version", "approved", "bindings", "entities"), ("music", "routines", "readonly_tools"))
        self.readonly_tools = data.get('readonly_tools')
        if self.readonly_tools is not None:
            permitted = {'home_discover', 'home_read', 'mnemosyne_recall', 'mnemosyne_get', 'web_search'}
            if type(self.readonly_tools) is not list or not self.readonly_tools or any(type(n) is not str or n not in permitted for n in self.readonly_tools) or len(set(self.readonly_tools)) != len(self.readonly_tools):
                raise ValueError('read-only tool allowlist')
            if data.get('music') or data.get('routines') or any(e.get('actions') for e in data['entities'].values()):
                raise ValueError('read-only policy cannot contain effect grants')
        if data["version"] != 1 or type(data["approved"]) is not bool:
            raise ValueError("policy version")
        if type(data["bindings"]) is not list or not data["bindings"]:
            raise ValueError("room binding required")
        self.bindings = {}
        for b in data["bindings"]:
            exact(b, ("device_id", "satellite_id", "area_id", "area_name"))
            for v in b.values(): plain(v, 128)
            if not ID.fullmatch(b['device_id']) or not ENTITY.fullmatch(b['satellite_id']) or not b['satellite_id'].startswith('assist_satellite.'):
                raise ValueError('finite physical binding required')
            key = (b["device_id"], b["satellite_id"])
            if key in self.bindings: raise ValueError("duplicate binding")
            self.bindings[key] = dict(b)
        if type(data["entities"]) is not dict or not data["entities"]:
            raise ValueError("no entities")
        self.entities = copy.deepcopy(data["entities"])
        for eid, row in self.entities.items():
            if not ENTITY.fullmatch(eid) or eid.split(".")[0] not in READ_DOMAINS:
                raise ValueError("unsafe entity")
            exact(row, ("name", "area_id", "actions"), ("arguments", "platform"))
            plain(row["name"], 200)
            if type(row["area_id"]) is not str or type(row["actions"]) is not list:
                raise ValueError("entity metadata")
            domain = eid.split(".")[0]
            if any(a not in ACTIONS.get(domain, {}) for a in row["actions"]):
                raise ValueError("unsupported action")
            # Garage/door/lock-like covers must NEVER be accidentally classified by this adapter.
            if domain == "cover" and row["actions"]:
                raise ValueError("cover actuation requires a separate qualified physical safety policy")
            if domain == 'switch' and row['actions'] and eid not in reviewed_switches:
                raise ValueError('unreviewed switch load/config/security hazard')
            for action, fields in row.get('arguments', {}).items():
                if action not in row['actions'] or set(fields) != set(ACTIONS[domain][action]): raise ValueError('action contract')
                Draft202012Validator.check_schema({'type':'object','properties':fields})
            if domain == 'select' and row['actions']:
                if eid not in select_options:
                    raise ValueError('finite reviewed select options required')
                options = list(select_options[eid])
                existing = row.get('arguments', {}).get('select_option', {}).get('option')
                if existing:
                    validator = Draft202012Validator(existing)
                    options = [o for o in options if validator.is_valid(o)]
                if not options:
                    raise ValueError('empty reviewed select intersection')
                row.setdefault('arguments', {})['select_option'] = {'option': {
                    'type': 'string', 'enum': options}}
            if domain in ('climate','media_player','select'):
                for action in row['actions']:
                    if any(isinstance(v,dict) and v.get('type')=='string' for v in ACTIONS[domain][action].values()) and action not in row.get('arguments',{}):
                        raise ValueError('live enum contract required')
        self.routines = copy.deepcopy(data.get('routines', {}))
        for name, routine in self.routines.items():
            if not ENTITY.fullmatch(name) or name.split('.')[0] not in ('scene','script','automation'): raise ValueError('routine name')
            exact(routine, ('name','steps','source_sha256'))
            if not re.fullmatch('[a-f0-9]{64}', routine['source_sha256']) or not 1 <= len(routine['steps']) <= 32: raise ValueError('routine review')
            for step in routine['steps']: self.action(step)
        self.music = copy.deepcopy(data.get("music"))
        if self.music:
            exact(self.music, ("server", "players", "schema_pins"))
            if self.music["server"] != "Music Assistant" or not self.music["players"]:
                raise ValueError("native Music Assistant grant")
            for pid, player in self.music["players"].items():
                plain(pid, 128); exact(player, ("name", "area_id")); plain(player["name"], 200)
            if set(self.music["schema_pins"]) != MUSIC_READ | MUSIC_EFFECT:
                raise ValueError("incomplete music schema qualification")
            if any(not re.fullmatch(r"[a-f0-9]{64}", p) for p in self.music["schema_pins"].values()):
                raise ValueError("schema fingerprint")
        self.approved = data["approved"]
        self.digest = hashlib.sha256(packed({'policy': data, 'reviewed_switches': sorted(reviewed_switches),
                                            'select_options': select_options}).encode()).hexdigest()

    def binding(self, ids):
        exact(ids, ("session_id", "turn_id", "device_id", "satellite_id"))
        if any(type(v) is not str or not ID.fullmatch(v) for k, v in ids.items() if k in ("session_id", "turn_id", "device_id")):
            raise ValueError("correlation")
        return self.bindings[(ids["device_id"], ids["satellite_id"])]

    def action(self, args):
        exact(args, ("entity_id", "action"), ("data",))
        eid, action = args["entity_id"], args["action"]
        if eid not in self.entities or action not in self.entities[eid]["actions"]:
            raise ValueError("target/action not granted")
        domain = eid.split(".")[0]
        limits = ACTIONS[domain][action]
        data = args.get("data", {})
        if type(data) is not dict or set(data) - set(limits):
            raise ValueError("service data")
        if action != 'turn_on':
            if set(data) != set(limits): raise ValueError("required action arguments")
        fields = action_fields(limits)
        Draft202012Validator({'type':'object','properties':fields,'additionalProperties':False}).validate(data)
        overrides = self.entities[eid].get('arguments', {}).get(action)
        if overrides: Draft202012Validator({'type':'object','properties':overrides,'additionalProperties':False}).validate(data)
        return domain, action, eid, data
