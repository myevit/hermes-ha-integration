"""Explicit construction only: registration never opens a database/network."""
import json
from functools import partial
from pathlib import Path

from .host import Host
from .policy import Policy
from .engine import Engine
from .provider import subscription_connection


def create_engine(ctx, policy_path, *, signed_request, reviewed_switches=(), select_options=None):
    from importlib.metadata import version
    for name, expected in (('mnemosyne-hermes', '0.7.1'), ('mnemosyne-memory', '3.15.1')):
        if version(name) != expected:
            raise ValueError('qualified memory dependency required: ' + name + '==' + expected)
    from hermes_state import SessionDB
    from tools.mcp_tool_discovery import discover_mcp_tools
    host = Host(ctx)
    policy = Policy(json.loads(Path(policy_path).read_text()), reviewed_switches=reviewed_switches,
                    select_options=select_options)
    if not policy.approved:
        raise ValueError('reviewed approved policy required')
    with host.scope_home():
        import tools.web_tools
        discover_mcp_tools(allowed_mcp_names=['homeassistant'])
        if policy.music:
            discover_mcp_tools(allowed_mcp_names=['Music Assistant'])
        db = SessionDB()
    if Path(db.db_path).resolve() != (host.home / 'state.db').resolve():
        db.close()
        raise ValueError('SessionDB does not belong to owning profile')
    return Engine(host, db, policy, partial(subscription_connection, host, signed_request))
