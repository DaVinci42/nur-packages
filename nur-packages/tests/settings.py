import importlib.util
import json
import os
import signal
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_module("configure", ROOT / "modules/fluxdown-configure.py")
generator = load_module("generator", ROOT / "pkgs/fluxdown-server/update-settings.py")
SCHEMA = json.loads((ROOT / "pkgs/fluxdown-server/settings-schema.json").read_text())


class SettingsTests(unittest.TestCase):
    def test_all_defaults(self):
        values = {}
        for name, field in SCHEMA["fields"].items():
            if field["kind"] != "ReadOnly":
                values[name] = (
                    json.loads(field["default"])
                    if field["kind"] in ("Bool", "Integer", "Float")
                    else field["default"]
                )
        self.assertEqual(len(helper.load_settings(values, None, SCHEMA)), 57)

    def test_invalid_values(self):
        for settings in [
            {"upload_limit_bytes": -1},
            {"upload_limit_bytes": True},
            {"max_concurrent_tasks": 1025},
            {"bt_enable_upnp": "false"},
            {"bt_mse_mode": "unknown"},
            {"bt_seed_ratio_limit": float("nan")},
            {"bt_seed_ratio_limit": float("inf")},
            {"domain_conn_caps": "x"},
            {"unknown": 1},
        ]:
            with (
                self.subTest(settings=settings),
                self.assertRaises(helper.ConfigurationError),
            ):
                helper.load_settings(settings, None, SCHEMA)

    def test_secret_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"proxy_password": "private-test-value"}))
            self.assertEqual(
                helper.load_settings({}, path, SCHEMA),
                {"proxy_password": "private-test-value"},
            )
            with self.assertRaises(helper.ConfigurationError):
                helper.load_settings({"proxy_password": "duplicate"}, path, SCHEMA)

    def test_null_and_endpoints(self):
        self.assertEqual(
            helper.load_settings({"upload_limit_bytes": None}, None, SCHEMA), {}
        )
        for bind, expected in [
            ("0.0.0.0:17800", "127.0.0.1:17800"),
            ("[::]:17800", "[::1]:17800"),
            ("192.168.42.42:17800", "192.168.42.42:17800"),
        ]:
            with patch.dict(os.environ, {"FLUXDOWN_BIND": bind}, clear=True):
                self.assertEqual(
                    helper.runtime_endpoint(),
                    (f"ws://{expected}/rpc", "/var/lib/fluxdown/agent/agent.token"),
                )

    def test_parser_fails_closed(self):
        prefix = "pub const DAEMON_CONFIG_FIELDS: &[DaemonConfigField] = &["
        self.assertEqual(
            generator.parse_fields(
                prefix + 'field("enabled", DaemonConfigKind::Bool, "false"),];'
            )["enabled"]["kind"],
            "Bool",
        )
        for entry in [
            "",
            'new_field("x"),',
            'field("x", DaemonConfigKind::NewType, ""),',
        ]:
            with self.assertRaises(ValueError):
                generator.parse_fields(prefix + entry + "];")

    def test_rpc_events_and_error_redaction(self):
        class Connection:
            def send(self, request):
                pass

            def settimeout(self, timeout):
                pass

            def recv(self):
                return next(self.responses)

        connection = Connection()
        connection.responses = iter(
            [
                json.dumps({"method": "event"}),
                json.dumps({"id": 1, "result": {"ok": True}}),
            ]
        )
        self.assertEqual(helper.RpcClient(connection).call("test"), {"ok": True})
        error = helper.RpcError({"message": "secret", "data": {"code": "conflict"}})
        self.assertTrue(error.retryable)
        self.assertNotIn("secret", str(error))

    def test_conflict_retry_and_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            token_file = Path(folder) / "agent.token"
            token_file.write_text("private-test-token")
            conflict = helper.RpcError({"data": {"code": "conflict"}})
            with (
                patch.object(helper.websocket, "create_connection"),
                patch.object(
                    helper.RpcClient,
                    "call",
                    side_effect=[
                        {},
                        {"revision": 1, "values": {}},
                        conflict,
                        {},
                        {"revision": 2, "values": {}},
                        {},
                    ],
                ) as calls,
                patch.object(helper.time, "sleep"),
            ):
                helper.apply_settings(
                    "ws://127.0.0.1:1/rpc", token_file, {"upload_limit_bytes": "1"}, 6
                )
                self.assertEqual(calls.call_count, 6)
                self.assertEqual(calls.call_args.args[1]["expectedRevision"], 2)
            with self.assertRaises(helper.ConfigurationError):
                helper.apply_settings(
                    "ws://127.0.0.1:1/rpc", token_file, {}, 6, timeout=0
                )

    @unittest.skipUnless(
        os.environ.get("FLUXDOWN_TEST_PACKAGE"),
        "Set FLUXDOWN_TEST_PACKAGE for isolated integration tests",
    )
    def test_live_server(self):
        with tempfile.TemporaryDirectory(prefix="fluxdown-settings-test-") as folder:
            reservations = [socket.socket(), socket.socket()]
            for reservation in reservations:
                reservation.bind(("127.0.0.1", 0))
            port, daemon_port = [
                reservation.getsockname()[1] for reservation in reservations
            ]
            for reservation in reservations:
                reservation.close()
            env = os.environ | {
                "FLUXDOWN_BIND": f"127.0.0.1:{port}",
                "FLUXDOWN_DAEMON_BIND": f"127.0.0.1:{daemon_port}",
                "FLUXDOWN_DAEMON_URL": f"ws://127.0.0.1:{daemon_port}/rpc",
                "FLUXDOWN_DATA_DIR": folder,
                "FLUXDOWN_SAVE_DIR": folder + "/downloads",
                "FLUXDOWN_MDNS": "false",
                "FLUXDOWN_ANALYTICS": "false",
            }
            url = f"ws://127.0.0.1:{port}/rpc"
            token_file = Path(folder) / "agent/agent.token"
            for iteration in range(2):
                with open(Path(folder) / "test.log", "w") as log:
                    process = subprocess.Popen(
                        [
                            os.environ["FLUXDOWN_TEST_PACKAGE"] + "/bin/fluxdown-agent",
                            "--server",
                        ],
                        env=env,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                    try:
                        values = (
                            {
                                "upload_limit_bytes": "1048576",
                                "max_concurrent_tasks": "3",
                                "bt_enable_upnp": "false",
                            }
                            if iteration == 0
                            else {}
                        )
                        helper.apply_settings(
                            url, token_file, values, SCHEMA["protocolVersion"]
                        )
                        connection = helper.websocket.create_connection(
                            url,
                            header={
                                "Authorization": "Bearer "
                                + token_file.read_text().strip()
                            },
                            suppress_origin=True,
                            timeout=5,
                            http_no_proxy=["*"],
                        )
                        try:
                            client = helper.RpcClient(connection)
                            client.call(
                                "system.hello",
                                {
                                    "clientName": "test",
                                    "clientVersion": "1",
                                    "minProtocolVersion": SCHEMA["protocolVersion"],
                                    "maxProtocolVersion": SCHEMA["protocolVersion"],
                                    "requestedRole": "agent",
                                    "capabilities": [],
                                },
                            )
                            snapshot = client.call("daemon.config.get")
                            self.assertEqual(
                                snapshot["values"]["upload_limit_bytes"], "1048576"
                            )
                            self.assertEqual(
                                snapshot["values"]["max_concurrent_tasks"], "3"
                            )
                            revision = snapshot["revision"]
                            helper.apply_settings(
                                url,
                                token_file,
                                {"upload_limit_bytes": "1048576"},
                                SCHEMA["protocolVersion"],
                            )
                            self.assertEqual(
                                client.call("daemon.config.get")["revision"], revision
                            )
                            if iteration == 0:
                                path = Path(folder) / "declared.json"
                                path.write_text(
                                    json.dumps({"speed_limit_bytes": 2097152})
                                )
                                subprocess.run(
                                    [
                                        os.sys.executable,
                                        str(ROOT / "modules/fluxdown-configure.py"),
                                        str(path),
                                        str(
                                            ROOT
                                            / "pkgs/fluxdown-server/settings-schema.json"
                                        ),
                                    ],
                                    env=env,
                                    check=True,
                                )
                            self.assertEqual(
                                client.call("daemon.config.get")["values"][
                                    "speed_limit_bytes"
                                ],
                                "2097152",
                            )
                            with self.assertRaises(helper.ConfigurationError):
                                helper.apply_settings(
                                    url,
                                    token_file,
                                    {"component_mirror_base": "http://invalid.test"},
                                    SCHEMA["protocolVersion"],
                                )
                        finally:
                            connection.close()
                    finally:
                        process.send_signal(signal.SIGTERM)
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        self.assertEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
