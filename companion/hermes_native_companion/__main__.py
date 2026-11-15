"""Explicit standalone lifecycle; no services installed, no credentials minted."""
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import ssl

from aiohttp import web
from .server import EngineBridge, create_app


def load_engine(manager, plugin_id, options):
    """0.23.1 compatibility seam, NOT a claimed Hermes native-engine registry.

    Discover only the explicitly selected profile's enabled plugins. The factory
    is the dependency plugin's public create_engine API, not an arbitrary file.
    """
    manager.discover_and_load()
    loaded = manager._plugins.get(plugin_id)
    if loaded is None or not loaded.enabled or loaded.module is None:
        raise ValueError("configured engine plugin is not loaded")
    factory = getattr(loaded.module, "create_engine", None)
    if not callable(factory):
        raise ValueError("plugin does not provide create_engine")
    return factory(**options)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--engine-plugin", required=True)
    parser.add_argument("--factory-options", required=True, type=Path,
                        help="Owner-only JSON kwargs for installed plugin create_engine")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--satellite-id", required=True)
    parser.add_argument("--credential-file", required=True, type=Path)
    parser.add_argument("--tls-cert", required=True)
    parser.add_argument("--tls-key", required=True)
    parser.add_argument("--exclusive-lock", required=True, type=Path,
                        help="Existing backend lifecycle lock; owner must approve replacement")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8444)
    args = parser.parse_args()
    # Must be chosen before Hermes imports; never an implicit default-profile run.
    home = args.home.resolve(strict=True)
    if args.profile == "default" or home.name != args.profile or home.parent.name != "profiles":
        parser.error("explicit named Hermes profile home required")
    for path in (args.credential_file, args.factory_options):
        if path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
            parser.error("configuration/credential file must be owned by this uid, mode 0600")
    lock = args.exclusive_lock.open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ["HERMES_HOME"] = str(home)
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.plugins import _plugin_home_scope
    with _plugin_home_scope(home):
        engine = load_engine(get_plugin_manager(), args.engine_plugin,
                             json.loads(args.factory_options.read_text()))
        bridge = EngineBridge(engine, profile=args.profile, device_id=args.device_id,
                              satellite_id=args.satellite_id)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(args.tls_cert, args.tls_key)
    app = create_app(bridge, args.credential_file.read_text().strip())
    async def close_engine(app):
        pending = tuple(getattr(engine, "pending", ()))
        if pending:
            # Keep lifecycle lock held until uncertain effects settle.
            await asyncio.gather(*pending, return_exceptions=True)
        engine.db.close()
    app.on_cleanup.append(close_engine)
    web.run_app(app, host=args.bind, port=args.port, ssl_context=tls,
                access_log=None, print=None)


if __name__ == "__main__":
    main()
