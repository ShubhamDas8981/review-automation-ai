"""Guardrails layer.

By default guardrails-ai exports usage traces/metrics to remote servers. This system
processes customer messages, so remote telemetry is switched off here (global flag)
and again per Guard via `disable_telemetry()` (Guard.__init__ reloads ~/.guardrailsrc,
which would otherwise re-enable it).
"""
try:
    from guardrails.settings import settings as _gr_settings

    _gr_settings.disable_tracing = True
    _gr_settings.rc.enable_metrics = False
except Exception:  # pragma: no cover - never let this break startup
    pass


def disable_telemetry(guard):
    """Call on every Guard right after building it."""
    try:
        guard.configure(allow_metrics_collection=False)
    except Exception:  # pragma: no cover
        pass
    return guard
