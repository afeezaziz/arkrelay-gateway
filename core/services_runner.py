import logging
import signal
import sys
import time

# Reuse the application's service initialization routine
from app import initialize_services

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("services_runner")

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}; shutting down services runner...")
    _shutdown = True

def main():
    logger.info("Starting services runner: initializing monitoring/performance/lightning/nostr/vtxo as configured...")
    try:
        # Initialize background services based on environment flags
        initialize_services()
        logger.info("Services initialized. Entering run loop.")
    except Exception as e:
        logger.exception(f"Service initialization failed: {e}")
        sys.exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Keep the process alive while background threads/services run
    try:
        while not _shutdown:
            time.sleep(5)
    except Exception:
        logger.exception("Unexpected error in services runner loop")
    finally:
        logger.info("Services runner exiting.")

if __name__ == "__main__":
    main()
