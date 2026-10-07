"""OpenTelemetry wiring (section 11). Every service calls `init_telemetry`
once at startup; if OTEL_EXPORTER_OTLP_ENDPOINT is unset (local dev,
tests), the OTel SDK's default no-op MeterProvider stays in place, so
every instrument call throughout the codebase is a harmless no-op instead
of needing its own "is telemetry configured?" branch.
"""

import logging

from opentelemetry import metrics

from reflight.core.config import get_settings

log = logging.getLogger("reflight.telemetry")

_initialized = False


def init_telemetry(service_name: str) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    settings = get_settings()
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        log.info("OTEL_EXPORTER_OTLP_ENDPOINT not set; metrics are no-ops")
        return

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": settings.otel_service_name, "service.instance": service_name})
    exporter = OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    log.info("telemetry initialized: service=%s endpoint=%s", service_name, endpoint)


def instrument_fastapi(app) -> None:
    settings = get_settings()
    if not settings.otel_exporter_otlp_endpoint:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
