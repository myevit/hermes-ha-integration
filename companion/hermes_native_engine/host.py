"""Genuine profile-owning PluginContext boundary."""
import contextlib
import copy
import json
from urllib.parse import urlencode
from pathlib import Path
from jsonschema import Draft202012Validator
from .policy import SOURCE, packed
from .capabilities import Capabilities


class Host:
    """Actual host context and API checks. No invented profile runtime object."""
    def __init__(self, ctx):
        from hermes_cli.plugins_context import PluginContext
        if not isinstance(ctx, PluginContext): raise TypeError("real PluginContext required")
        self.ctx = ctx
        self.home = Path(ctx._manager.home_path).resolve()
        if self.home.parent.name != "profiles" or self.home.name == "default" or not self.home.name:
            raise ValueError("explicit named owning profile required")
        self.profile = self.home.name
        self.scope = ctx._manager.scope_key
        with self.scope_home():
            if ctx.profile_name != self.profile:
                raise ValueError("host does not recognize this home as the actual owning profile")

    @contextlib.contextmanager
    def scope_home(self):
        from hermes_cli.plugins import _plugin_home_scope
        with _plugin_home_scope(self.home): yield

    @staticmethod
    def wire_name(name):
        # State reads deliberately use the profile's existing chosen MCP, never
        # the unprefixed builtin REST adapter or another profile's credentials.
        return 'mcp__homeassistant__ha_get_state' if name == 'ha_get_state' else name

    def actual_schema(self, name):
        from tools.registry import registry
        entry = registry.get_entry(self.wire_name(name), scope=self.scope)
        if entry is None: raise ValueError("required host capability absent: " + name)
        return copy.deepcopy(entry.schema)

    def dispatch(self, name, args, sid):
        # Called in an awaited executor. Context is explicitly rebound in that thread.
        with self.scope_home():
            Draft202012Validator(self.actual_schema(name)["parameters"]).validate(args)
            result = self.ctx.dispatch_tool(self.wire_name(name), args, session_id=sid)
        result = json.loads(result) if isinstance(result, str) else result
        if not isinstance(result, (dict, list)) or (isinstance(result, dict) and result.get("error")):
            raise ValueError("host tool failed: " + name)
        if len(packed(result)) > 48000: raise ValueError("host result budget")
        return result

    def discover_entities(self, rows, sid):
        """Intersect live MCP registry discovery with reviewed grants, never broaden them."""
        found = {}
        for domain in sorted({r['entity_id'].split('.')[0] for r in rows}):
            offset, seen = 0, set()
            for _ in range(20):
                result = Capabilities._music_value(self.dispatch('mcp__homeassistant__ha_search', {
                    'domain_filter': domain, 'limit': 100, 'offset': offset,
                    'include_hidden': False, 'result_fields': ['entity_id', 'name'],
                    'fields': ['entities'], 'exact_match': True}, sid))
                if result.get('success') is not True or result.get('partial') or result.get('errors'):
                    raise ValueError('incomplete live discovery')
                for row in result['entities']:
                    found[row['entity_id']] = row
                if not result.get('entity_has_more', result.get('has_more', False)): break
                offset = result.get('entity_next_offset', result.get('next_offset'))
                if type(offset) is not int or offset in seen: raise ValueError('discovery pagination')
                seen.add(offset)
            else: raise ValueError('discovery page budget')
        return [dict(row, name=found[row['entity_id']].get('name', row['name']))
                for row in rows if row['entity_id'] in found]

    def household_read(self, kind, args):
        """Two fixed read-only HA operations via the installed authenticated transport."""
        from . import rest as ha
        with self.scope_home():
            if kind == 'home_forecast':
                return ha._run_async(ha._api_json('POST', '/api/services/weather/get_forecasts?return_response', 15,
                    {'entity_id':args['entity_id'], 'type':args['type']}))
            if kind == 'home_history':
                query = urlencode({'filter_entity_id':args['entity_id'], 'minimal_response':'1','no_attributes':'1'})
                return ha._run_async(ha._api_json('GET', '/api/history/period?' + query, 15))
        raise ValueError('readonly operation')

    def persona(self):
        from agent.prompt_builder import load_soul_md
        with self.scope_home(): value = load_soul_md(home_override=self.home)
        if not value: raise ValueError("profile identity missing")
        return value

    def memory(self, sid, key, db=None):
        from hermes_cli.config import load_config_readonly
        from plugins.memory import load_memory_provider
        from agent.memory_manager import MemoryManager
        with self.scope_home():
            config = load_config_readonly()
            mem = config.get("memory", {})
            if mem.get("provider") != "mnemosyne": raise ValueError("profile Mnemosyne required")
            provider = load_memory_provider("mnemosyne")
            if provider is None or not provider.is_available(): raise ValueError("Mnemosyne unavailable")
            manager = MemoryManager()
            manager.add_provider(provider)
            kwargs = dict(mem.get("mnemosyne", {}))
            from hermes_cli.profiles import get_active_profile_name
            identity = get_active_profile_name()
            if identity != self.profile: raise ValueError("profile memory identity mismatch")
            count = int((db.get_session_list_row(sid) or {}).get("message_count") or 0) if db else 0
            resumed = bool(db and db.latest_message_row_id(sid, role="assistant", require_text=False) is not None)
            title = db.get_session_title(sid) if db else None
            manager.initialize_all(session_id=sid, hermes_home=str(self.home), agent_identity=identity,
                                   agent_workspace="hermes", agent_context="primary", gateway_session_key=key,
                                   chat_id=key, chat_type="group", platform=SOURCE, resumed=resumed,
                                   message_count=count, session_title=title, **kwargs)
            # The provider reports initialization health through native hooks.
            if not manager.build_system_prompt() or getattr(provider, "_beam", None) is None:
                manager.release_soft()
                raise ValueError("Mnemosyne initialization unavailable")
            return manager
