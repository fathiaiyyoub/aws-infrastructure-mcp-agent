import asyncio
import contextlib
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from security import (
    APPROVAL_ENV, SafeToolError, make_approval_grant, redact_text,
    redact_value, require_terraform_approval, safe_tool_result,
)
from mcp_server import terraform_tools as tf
from mcp_client import client
from agent import agent as app


class TerraformSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.patch_dir = patch.object(tf, "TERRAFORM_DIR", self.base)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.proc = patch.object(tf.subprocess, "run")
        self.run = self.proc.start()
        self.addCleanup(self.proc.stop)
        self.run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        self.digest = hashlib.sha256(b"synthetic saved plan").hexdigest()

    def grant(self, operation="apply", digest=None):
        os.environ[APPROVAL_ENV] = make_approval_grant(operation, digest or self.digest)

    def plan_file(self):
        (self.base / "tfplan").write_bytes(b"synthetic saved plan")

    def test_configuration_round_trip_and_listing(self):
        for name in ("main.tf", "variables.tf", "example.tf.json"):
            self.assertIn("written", tf.write_terraform_file(name, "{}"))
            self.assertEqual(tf.read_terraform_file(name), "{}")
        (self.base / "terraform.tfstate").write_text("private")
        self.assertEqual(tf.list_terraform_files(), ["example.tf.json", "main.tf", "variables.tf"])
        self.run.assert_not_called()

    def test_non_configuration_and_path_escapes_rejected(self):
        for name in ("../escape.tf", r"..\escape.tf", "/escape.tf", r"C:\escape.tf",
                     "main.tf:stream.tf", ".env", "terraform.tfstate", "secret.tfvars", "tfplan"):
            with self.subTest(name=name):
                self.assertIn("Access denied", tf.read_terraform_file(name))
                self.assertIn("Rejected", tf.write_terraform_file(name, "private"))
        self.run.assert_not_called()

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "outside.tf"
            target.write_text("unchanged")
            link = self.base / "linked.tf"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Host does not permit creating symlinks")
            self.assertIn("Access denied", tf.read_terraform_file(link.name))
            self.assertIn("Rejected", tf.write_terraform_file(link.name, "changed"))
            self.assertNotIn(link.name, tf.list_terraform_files())
            self.assertEqual(target.read_text(), "unchanged")

    def test_reparse_point_rejected(self):
        with patch.object(tf, "_is_link", return_value=True):
            self.assertIn("Rejected", tf.write_terraform_file("main.tf", "{}"))
            self.assertIn("Access denied", tf.read_terraform_file("main.tf"))

    def test_external_hardlink_reads_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "private.txt"
            content = "private outside fixture"
            target.write_text(content, encoding="utf-8")
            for name in ("linked.tf", "linked.tf.json"):
                with self.subTest(name=name):
                    link = self.base / name
                    os.link(target, link)
                    self.assertGreater(link.stat().st_nlink, 1)
                    result = tf.read_terraform_file(name)
                    self.assertIn("Access denied", result)
                    self.assertNotIn(content, result)
                    self.assertNotIn(name, tf.list_terraform_files())
            self.assertEqual(target.read_text(encoding="utf-8"), content)
        self.run.assert_not_called()

    def test_atomic_write_does_not_modify_hardlink_target(self):
        target = self.base / "original.tf"
        target.write_text("unchanged")
        os.link(target, self.base / "linked.tf")
        tf.write_terraform_file("linked.tf", "replacement")
        self.assertEqual(target.read_text(), "unchanged")

    def test_missing_approval_rejects_apply_and_destroy(self):
        self.plan_file()
        for function in (tf.apply_terraform, tf.destroy_terraform):
            with self.assertRaisesRegex(SafeToolError, "terminal-approved"):
                function(self.digest)
        self.run.assert_not_called()

    def test_missing_and_modified_plans_rejected(self):
        for function, operation in ((tf.apply_terraform, "apply"), (tf.destroy_terraform, "destroy")):
            (self.base / "tfplan").unlink(missing_ok=True)
            self.grant(operation)
            with self.assertRaisesRegex(SafeToolError, "missing"):
                function(self.digest)
            (self.base / "tfplan").write_bytes(b"changed")
            self.grant(operation)
            with self.assertRaisesRegex(SafeToolError, "changed"):
                function(self.digest)
        self.run.assert_not_called()

    def test_operation_hash_and_expiry_binding(self):
        self.plan_file()
        for grant in (
            make_approval_grant("destroy", self.digest),
            make_approval_grant("apply", "0" * 64),
            json.dumps({"operation": "apply", "sha256": self.digest, "expires": time.time() - 1}),
            "invalid", "[]",
        ):
            os.environ[APPROVAL_ENV] = grant
            with self.assertRaises(SafeToolError):
                tf.apply_terraform(self.digest)
            self.assertNotIn(APPROVAL_ENV, os.environ)
        self.run.assert_not_called()

    def test_authorised_apply_and_destroy_use_saved_plan_once(self):
        self.plan_file()
        for function, operation in ((tf.apply_terraform, "apply"), (tf.destroy_terraform, "destroy")):
            self.grant(operation)
            self.assertEqual(function(self.digest), "ok")
            self.assertEqual(self.run.call_args.args[0], ["terraform", "apply", "-no-color", "tfplan"])
            with self.assertRaises(SafeToolError):
                function(self.digest)
        self.assertEqual(self.run.call_count, 2)

    def test_failed_execution_returns_safe_error(self):
        self.plan_file()
        self.grant()
        self.run.return_value = SimpleNamespace(returncode=1, stdout="private diagnostic", stderr="private")
        with self.assertRaises(SafeToolError) as caught:
            tf.apply_terraform(self.digest)
        self.assertNotIn("private", str(caught.exception))

    def test_failed_plan_removes_stale_plan_and_hides_output(self):
        for function in (tf.plan_terraform, tf.plan_terraform_destroy):
            self.plan_file()
            self.run.return_value = SimpleNamespace(returncode=1, stdout="private", stderr="private")
            with self.assertRaises(SafeToolError) as caught:
                function()
            self.assertNotIn("private", str(caught.exception))
            self.assertFalse((self.base / "tfplan").exists())

    def test_plan_fingerprint_and_destroy_flag(self):
        def fake_run(command, **kwargs):
            if command[1] == "plan":
                self.plan_file()
            return SimpleNamespace(returncode=0, stdout="Plan: 1 to add, 0 to change, 0 to destroy.", stderr="")
        self.run.side_effect = fake_run
        for function, destroy in ((tf.plan_terraform, False), (tf.plan_terraform_destroy, True)):
            self.run.reset_mock()
            result = function()
            self.assertEqual(result["plan_sha256"], self.digest)
            self.assertEqual("-destroy" in self.run.call_args_list[0].args[0], destroy)
            self.assertEqual(self.run.call_args_list[1].args[0][1], "show")

    def test_plan_changed_during_display_is_rejected(self):
        def fake_run(command, **kwargs):
            (self.base / "tfplan").write_bytes(b"first" if command[1] == "plan" else b"changed")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        self.run.side_effect = fake_run
        for function in (tf.plan_terraform, tf.plan_terraform_destroy):
            with self.assertRaisesRegex(SafeToolError, "changed"):
                function()

    def test_validate_keeps_command_and_redacts(self):
        self.run.return_value = SimpleNamespace(returncode=0, stdout='password = "synthetic-value"', stderr="")
        self.assertNotIn("synthetic-value", tf.validate_terraform())
        self.assertEqual(self.run.call_args.args[0], ["terraform", "validate", "-no-color"])


class OutputAndCredentialTests(unittest.TestCase):
    def test_runtime_credentials_and_common_patterns_redacted(self):
        synthetic = "fixture-only-runtime-value"
        with patch.dict(os.environ, {"OPENAI_API_KEY": synthetic}, clear=True):
            self.assertNotIn(synthetic, redact_text("error: " + synthetic))
        for text in ('password = "fixture-secret"', 'Authorization: Bearer fixture-value',
                     'postgres://test:fixture-password@example.invalid/db',
                     "sk-" + "x" * 32, "AKIA" + "X" * 16):
            self.assertIn("[REDACTED]", redact_text(text))
        self.assertEqual(redact_value({"aws_secret_access_key": "fixture"})["aws_secret_access_key"], "[REDACTED]")

    def test_provider_exception_suppressed(self):
        @safe_tool_result
        def failing():
            raise ValueError("sensitive-provider-detail")
        with self.assertRaises(SafeToolError) as caught:
            failing()
        self.assertNotIn("sensitive-provider-detail", str(caught.exception))

    def test_aws_runtime_environment_forwarded_but_not_openai_or_ambient_grant(self):
        with patch.dict(os.environ, {"AWS_PROFILE": "demo", "AWS_SESSION_TOKEN": "fixture-only",
                                    "OPENAI_API_KEY": "fixture-only", APPROVAL_ENV: "ambient"}, clear=True):
            params = client.build_server_params()
            self.assertEqual(params.env["AWS_PROFILE"], "demo")
            self.assertEqual(params.env["AWS_SESSION_TOKEN"], "fixture-only")
            self.assertNotIn("OPENAI_API_KEY", params.env)
            self.assertNotIn(APPROVAL_ENV, params.env)
            self.assertEqual(client.build_server_params("explicit").env[APPROVAL_ENV], "explicit")

    def test_openai_sdk_reads_runtime_key_without_network(self):
        from openai import AsyncOpenAI
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-only-not-a-real-key"}):
            sdk = AsyncOpenAI()
            self.assertEqual(sdk.api_key, os.environ["OPENAI_API_KEY"])
            asyncio.run(sdk.close())

    def test_boto3_provider_chain_reads_environment_without_network(self):
        import boto3
        clean_env = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}
        clean_env.update({"AWS_ACCESS_KEY_ID": "fixture-id", "AWS_SECRET_ACCESS_KEY": "fixture-secret",
                          "AWS_EC2_METADATA_DISABLED": "true", "AWS_CONFIG_FILE": os.devnull,
                          "AWS_SHARED_CREDENTIALS_FILE": os.devnull})
        with patch.dict(os.environ, clean_env, clear=True):
            credentials = boto3.Session().get_credentials()
            self.assertEqual(credentials.method, "env")
            self.assertEqual(credentials.access_key, "fixture-id")


class AgentApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def tools(self):
        names = ("apply_terraform_tool", "destroy_terraform_tool", "read_terraform_file_tool")
        tools = [SimpleNamespace(name=name, description=name,
                 input_schema={"type": "object", "properties": {}, "additionalProperties": False}) for name in names]
        with patch.object(app, "get_tools", AsyncMock(return_value=SimpleNamespace(tools=tools))):
            return {tool.name: tool for tool in await app.build_agent_tools()}

    def plan(self):
        return SimpleNamespace(is_error=False, structured_content={"plan": "Plan: 0 to add, 0 to change, 0 to destroy.",
                              "plan_sha256": "a" * 64}, content=[])

    async def test_rejection_never_calls_execution_path(self):
        tools = await self.tools()
        for name in ("apply_terraform_tool", "destroy_terraform_tool"):
            with patch.object(app, "call_tool", AsyncMock(return_value=self.plan())) as normal, \
                 patch.object(app, "call_approved_terraform_tool", AsyncMock()) as approved, \
                 patch("builtins.input", return_value="no"), contextlib.redirect_stdout(io.StringIO()):
                result = await tools[name].on_invoke_tool(None, "{}")
            self.assertIn("rejected", result)
            approved.assert_not_awaited()
            self.assertEqual(normal.await_count, 1)

    async def test_approval_uses_trusted_path_and_authoritative_hash(self):
        tools = await self.tools()
        for name, planning in (("apply_terraform_tool", "plan_terraform_tool"),
                               ("destroy_terraform_tool", "plan_terraform_destroy_tool")):
            with patch.object(app, "call_tool", AsyncMock(return_value=self.plan())) as normal, \
                 patch.object(app, "call_approved_terraform_tool", AsyncMock(return_value=SimpleNamespace(structured_content={"ok": True}))) as approved, \
                 patch("builtins.input", return_value="yes"), contextlib.redirect_stdout(io.StringIO()):
                result = await tools[name].on_invoke_tool(None, '{"plan_sha256":"untrusted-model-value"}')
            normal.assert_awaited_once_with(planning, {})
            approved.assert_awaited_once_with(name, "a" * 64)
            self.assertEqual(result, {"ok": True})

    async def test_failed_plan_never_prompts_or_executes(self):
        tools = await self.tools()
        plan = SimpleNamespace(is_error=True, content="sensitive-diagnostic")
        output = io.StringIO()
        with patch.object(app, "call_tool", AsyncMock(return_value=plan)), \
             patch.object(app, "call_approved_terraform_tool", AsyncMock()) as approved, \
             patch("builtins.input") as prompt, contextlib.redirect_stdout(output):
            await tools["apply_terraform_tool"].on_invoke_tool(None, "{}")
        approved.assert_not_awaited()
        prompt.assert_not_called()
        self.assertNotIn("sensitive-diagnostic", output.getvalue())

    async def test_argument_values_are_not_logged(self):
        tools = await self.tools()
        output = io.StringIO()
        with patch.object(app, "call_tool", AsyncMock(return_value=SimpleNamespace(structured_content={"ok": True}))), \
             contextlib.redirect_stdout(output):
            await tools["read_terraform_file_tool"].on_invoke_tool(None, '{"content":"private-configuration"}')
        self.assertNotIn("private-configuration", output.getvalue())
        self.assertIn("read_terraform_file_tool", output.getvalue())


class AgentRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_cost_request_and_report_with_model_mocked(self):
        result = SimpleNamespace(new_items=[], final_output="Synthetic cost report")
        output = io.StringIO()
        with patch.object(app, "build_agent_tools", AsyncMock(return_value=[])), \
             patch.object(app, "get_resources", AsyncMock(return_value=SimpleNamespace(resources=[]))), \
             patch.object(app, "get_prompts", AsyncMock(return_value=SimpleNamespace(prompts=[]))), \
             patch.object(app.Runner, "run", AsyncMock(return_value=result)) as runner, \
             contextlib.redirect_stdout(output):
            await app.main()
        self.assertIn("Estimate the monthly AWS infrastructure cost", runner.call_args.args[1])
        self.assertTrue(runner.call_args.kwargs["run_config"].tracing_disabled)
        self.assertFalse(runner.call_args.kwargs["run_config"].trace_include_sensitive_data)
        self.assertIn("Synthetic cost report", output.getvalue())


if __name__ == "__main__":
    unittest.main()
