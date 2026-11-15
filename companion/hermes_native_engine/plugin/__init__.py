"""Installable owning-profile shim. Import/register performs no activation."""
_CTX = None


def register(ctx):
    global _CTX
    from hermes_native_engine.host import Host
    Host(ctx)
    _CTX = ctx


def get_ctx():
    if _CTX is None:
        raise RuntimeError('native engine plugin not loaded by Hermes')
    return _CTX


def signed_request(method, url, **kwargs):
    # Keep this frame in the installed plugin directory: the SDK verifies its
    # manifest and signs using the active owning profile. No token escapes.
    from hermes_cli.plugin_provider_requests import credentialed_provider_request
    return credentialed_provider_request('openai-codex', method, url, **kwargs)


def create_engine(policy_path, *, reviewed_switches=(), select_options=None):
    from hermes_native_engine.factory import create_engine as factory
    return factory(get_ctx(), policy_path, signed_request=signed_request,
                   reviewed_switches=reviewed_switches, select_options=select_options)
