import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import websocket


class ConfigurationError(Exception):
    pass


class RpcError(Exception):
    def __init__(self, error):
        data = error.get("data", {})
        self.retryable = data.get("retryable", False) or data.get("code") in (
            "conflict",
            "unavailable",
            "timeout",
        )
        super().__init__("FluxDown rejected the settings RPC")


def load_settings(declared, secret_file, schema):
    values = dict(declared)
    if secret_file:
        private = json.loads(Path(secret_file).read_text())
        if not isinstance(private, dict):
            raise ConfigurationError("settingsFile must contain a JSON object")
        if values.keys() & private.keys():
            raise ConfigurationError(
                "settings and settingsFile must not contain duplicate keys"
            )
        values.update(private)
    result = {}
    for name, value in values.items():
        field = schema["fields"].get(name)
        if field is None or field["kind"] == "ReadOnly":
            raise ConfigurationError("Unknown or read-only daemon setting")
        if value is None:
            continue
        kind = field["kind"]
        if kind == "Bool":
            valid = type(value) is bool
        elif kind == "Integer":
            valid = type(value) is int and field["min"] <= value <= field["max"]
        elif kind == "Float":
            valid = (
                type(value) in (int, float)
                and math.isfinite(value)
                and value >= field["min"]
            )
        elif kind == "Enum":
            valid = isinstance(value, str) and value in field["values"]
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ConfigurationError("Invalid daemon setting type or range")
        result[name] = ("true" if value else "false") if kind == "Bool" else str(value)
    return result


class RpcClient:
    def __init__(self, connection):
        self.connection = connection
        self.sequence = 0

    def call(self, method, params=None):
        self.sequence += 1
        request = {"jsonrpc": "2.0", "id": self.sequence, "method": method}
        if params is not None:
            request["params"] = params
        self.connection.send(json.dumps(request))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.connection.settimeout(max(0.01, deadline - time.monotonic()))
            response = json.loads(self.connection.recv())
            if response.get("id") != self.sequence:
                continue
            if "error" in response:
                raise RpcError(response["error"])
            return response["result"]
        raise TimeoutError("RPC response timed out")


def apply_settings(url, token_file, values, protocol, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        connection = None
        try:
            token = Path(token_file).read_text().strip()
            if not token:
                raise OSError("Agent token is not ready")
            connection = websocket.create_connection(
                url,
                header={"Authorization": "Bearer " + token},
                suppress_origin=True,
                timeout=5,
                http_no_proxy=["*"],
            )
            client = RpcClient(connection)
            client.call(
                "system.hello",
                {
                    "clientName": "nixos-settings",
                    "clientVersion": "1",
                    "minProtocolVersion": protocol,
                    "maxProtocolVersion": protocol,
                    "requestedRole": "agent",
                    "capabilities": [],
                },
            )
            snapshot = client.call("daemon.config.get")
            changes = {
                name: value
                for name, value in values.items()
                if snapshot["values"].get(name) != value
            }
            if changes:
                client.call(
                    "daemon.config.patch",
                    {"expectedRevision": snapshot["revision"], "values": changes},
                )
            return
        except RpcError as error:
            if not error.retryable:
                raise ConfigurationError(
                    "FluxDown rejected declared settings; check the pinned upstream contract"
                ) from None
        except (OSError, websocket.WebSocketException):
            pass
        finally:
            if connection is not None:
                connection.close()
        time.sleep(0.2)
    raise ConfigurationError("Timed out applying settings to FluxDown")


def runtime_endpoint():
    bind = os.environ.get("FLUXDOWN_BIND", "127.0.0.1:17800")
    host, port = bind.rsplit(":", 1)
    host = {"0.0.0.0": "127.0.0.1", "[::]": "[::1]"}.get(host, host)
    root = Path(os.environ.get("FLUXDOWN_DATA_DIR", "/var/lib/fluxdown"))
    agent_dir = Path(os.environ.get("FLUXDOWN_AGENT_DATA_DIR", str(root / "agent")))
    token_file = os.environ.get(
        "FLUXDOWN_AGENT_TOKEN_FILE", str(agent_dir / "agent.token")
    )
    return f"ws://{host}:{port}/rpc", token_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("settings")
    parser.add_argument("schema")
    parser.add_argument("--settings-file")
    args = parser.parse_args()
    try:
        schema = json.loads(Path(args.schema).read_text())
        values = load_settings(
            json.loads(Path(args.settings).read_text()), args.settings_file, schema
        )
        if values:
            url, token_file = runtime_endpoint()
            apply_settings(url, token_file, values, schema["protocolVersion"])
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, websocket.WebSocketException):
        print(
            "Failed to apply FluxDown settings; check file permissions and configuration",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
