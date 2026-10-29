import logging


def setup_logging(level: str = "INFO") -> None:
    """Console logging. We log model name, latency and token counts - never API keys or inquiry text."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full URLs at INFO
