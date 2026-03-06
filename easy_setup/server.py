"""
=============================================================================
TradingView Webhook → MT4 Bridge Server
=============================================================================
Receives JSON alerts from TradingView webhooks and writes trade signal
files that the MT4 EA reads and executes.

Usage:
    python server.py                        # Runs on default port 5000
    python server.py --port 8080            # Custom port
    python server.py --port 8080 --token mysecretkey  # With auth token
=============================================================================
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================
DEFAULT_PORT = 5000
SIGNALS_DIR = None       # Set via args or auto-detect MT4 path
AUTH_TOKEN = None         # Optional webhook authentication token
LOG_FILE = "webhook_bridge.log"

# =============================================================================
# LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("WebhookBridge")

# =============================================================================
# SIGNAL FILE WRITER
# =============================================================================
def write_signal(signal_data):
    """
    Writes a trade signal file that the MT4 EA will read.
    File format: JSON with timestamp, action, symbol, lot, sl, tp, comment
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"signal_{timestamp}.json"
    filepath = os.path.join(SIGNALS_DIR, filename)

    # Add metadata
    signal_data["timestamp"] = datetime.utcnow().isoformat()
    signal_data["status"] = "pending"

    try:
        with open(filepath, "w") as f:
            json.dump(signal_data, f, indent=2)
        logger.info(f"Signal written: {filepath}")
        logger.info(f"Signal data: {json.dumps(signal_data)}")
        return True, filepath
    except Exception as e:
        logger.error(f"Failed to write signal: {e}")
        return False, str(e)


# =============================================================================
# WEBHOOK HANDLER
# =============================================================================
class WebhookHandler(BaseHTTPRequestHandler):
    """Handles incoming webhook POST requests from TradingView."""

    def do_POST(self):
        """Process TradingView webhook alert."""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            logger.info(f"Received webhook: {body}")

            # Parse JSON
            try:
                signal = json.loads(body)
            except json.JSONDecodeError:
                # TradingView sometimes sends plain text
                # Try to parse as key=value format
                logger.warning(f"Non-JSON payload received: {body}")
                self._send_response(400, {"error": "Invalid JSON"})
                return

            # Validate auth token if configured
            if AUTH_TOKEN:
                token = signal.get("token", "")
                if token != AUTH_TOKEN:
                    logger.warning(f"Invalid auth token: {token}")
                    self._send_response(401, {"error": "Unauthorized"})
                    return

            # Validate required fields
            action = signal.get("action", "").lower()
            if action not in ["buy", "sell", "close_buy", "close_sell", "close_all"]:
                logger.warning(f"Invalid action: {action}")
                self._send_response(400, {"error": f"Invalid action: {action}"})
                return

            # Write signal file for MT4 EA
            success, result = write_signal(signal)

            if success:
                self._send_response(200, {
                    "status": "ok",
                    "message": f"Signal processed: {action}",
                    "file": result
                })
            else:
                self._send_response(500, {"error": f"Failed to write signal: {result}"})

        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            self._send_response(500, {"error": str(e)})

    def do_GET(self):
        """Health check endpoint."""
        self._send_response(200, {
            "status": "running",
            "service": "TradingView-MT4 Webhook Bridge",
            "signals_dir": SIGNALS_DIR,
            "time": datetime.utcnow().isoformat()
        })

    def _send_response(self, code, data):
        """Send JSON response."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        """Override default logging to use our logger."""
        logger.info(f"HTTP: {args[0]}")


# =============================================================================
# MT4 DATA DIRECTORY DETECTION
# =============================================================================
def find_mt4_data_dir():
    """
    Tries to auto-detect the MT4 data directory.
    Returns the MQL4/Files path where signal files should be written.
    """
    # Common MT4 data directory locations on Windows
    possible_paths = []

    # Check APPDATA (most common)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        mt4_base = os.path.join(appdata, "MetaQuotes", "Terminal")
        if os.path.exists(mt4_base):
            # Find terminal directories
            for item in os.listdir(mt4_base):
                mql_files = os.path.join(mt4_base, item, "MQL4", "Files")
                if os.path.exists(mql_files):
                    possible_paths.append(mql_files)

    if possible_paths:
        logger.info(f"Found MT4 data directories: {possible_paths}")
        return possible_paths[0]  # Return first found

    return None


# =============================================================================
# MAIN
# =============================================================================
def main():
    global SIGNALS_DIR, AUTH_TOKEN

    parser = argparse.ArgumentParser(description="TradingView → MT4 Webhook Bridge")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})")
    parser.add_argument("--signals-dir", type=str, default=None,
                        help="Directory for signal files (default: auto-detect MT4 or ./signals/)")
    parser.add_argument("--token", type=str, default=None,
                        help="Authentication token for webhook security")
    args = parser.parse_args()

    AUTH_TOKEN = args.token

    # Determine signals directory
    if args.signals_dir:
        SIGNALS_DIR = args.signals_dir
    else:
        # Try auto-detect MT4
        mt4_dir = find_mt4_data_dir()
        if mt4_dir:
            SIGNALS_DIR = mt4_dir
            logger.info(f"Auto-detected MT4 directory: {SIGNALS_DIR}")
        else:
            SIGNALS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals")
            logger.info(f"MT4 not found, using local directory: {SIGNALS_DIR}")

    # Create signals directory
    os.makedirs(SIGNALS_DIR, exist_ok=True)

    # Start server
    server = HTTPServer(("0.0.0.0", args.port), WebhookHandler)
    logger.info("=" * 60)
    logger.info("TradingView → MT4 Webhook Bridge")
    logger.info("=" * 60)
    logger.info(f"Server running on port {args.port}")
    logger.info(f"Signals directory: {SIGNALS_DIR}")
    logger.info(f"Auth token: {'Enabled' if AUTH_TOKEN else 'Disabled'}")
    logger.info(f"Webhook URL: http://YOUR_IP:{args.port}/")
    logger.info("=" * 60)
    logger.info("Waiting for TradingView alerts...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
