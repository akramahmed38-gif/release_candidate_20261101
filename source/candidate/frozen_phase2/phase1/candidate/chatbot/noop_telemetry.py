"""Disable optional Chroma product telemetry in the offline deployment."""
from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent
from overrides import override


class DisabledProductTelemetry(ProductTelemetryClient):
    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        # Do not initialize an analytics SDK or collect a telemetry user ID.
        return None
