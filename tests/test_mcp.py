"""Offline integration tests: real stdio MCP, no cloud or Terraform calls."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from agent import agent as app
from mcp_client import client
from mcp_server import aws_tools

EXPECTED_TOOLS = {
    "get_server_status", "get_aws_region", "describe_aws_region",
    "list_ec2_instances_tool", "list_vpcs_tool", "list_subnets_tool",
    "list_acm_certificates_tool", "validate_terraform_tool", "plan_terraform_tool",
    "write_terraform_file_tool", "read_terraform_file_tool", "list_terraform_files_tool",
    "apply_terraform_tool", "destroy_terraform_tool", "plan_terraform_destroy_tool",
}


class MCPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_real_agent_registration(self):
        result = await asyncio.wait_for(client.get_tools(), timeout=30)
        self.assertEqual({tool.name for tool in result.tools}, EXPECTED_TOOLS)
        with patch.object(app, "get_tools", AsyncMock(return_value=result)):
            tools = await app.build_agent_tools()
        self.assertEqual({tool.name for tool in tools}, EXPECTED_TOOLS)

    async def test_status_resources_and_cost_prompt(self):
        status = await asyncio.wait_for(client.call_tool("get_server_status"), timeout=30)
        self.assertFalse(status.is_error)
        resources = await client.get_resources()
        self.assertEqual({str(item.uri) for item in resources.resources},
                         {"policy://deployment", "standards://aws-tagging", "deployment://environment"})
        policy = await client.read_resource("policy://deployment")
        self.assertIn("DEPLOYMENT POLICY", policy.contents[0].text)
        prompts = await client.get_prompts()
        self.assertEqual({item.name for item in prompts.prompts},
                         {"estimate-aws-cost", "aws-security-review", "aws-resilience-review"})
        prompt = await client.get_prompt("estimate-aws-cost", {"terraform_configuration": "# synthetic configuration"})
        text = "\n".join(message.content.text for message in prompt.messages)
        self.assertIn("# synthetic configuration", text)
        self.assertIn("Pricing Evidence Decision Rules", text)
        self.assertIn("730", text)

    async def test_direct_mcp_execution_without_grant_is_denied(self):
        for name in ("apply_terraform_tool", "destroy_terraform_tool"):
            result = await client.call_tool(name, {"plan_sha256": "a" * 64})
            self.assertTrue(result.is_error)
            self.assertIn("Error executing tool", str(result.content))

    async def test_state_read_is_denied_over_mcp(self):
        result = await client.call_tool("read_terraform_file_tool", {"filename": "terraform.tfstate.backup"})
        self.assertIn("Access denied", str(result.content))


class AWSDiscoveryTests(unittest.TestCase):
    def test_all_discovery_functions_use_mocked_boto3(self):
        cases = [
            (aws_tools.list_ec2_instances, "describe_instances", {"Reservations": [{"Instances": [
                {"InstanceId": "fixture", "State": {"Name": "running"}, "InstanceType": "t3.micro"}]}]}),
            (aws_tools.list_vpcs, "describe_vpcs", {"Vpcs": [
                {"VpcId": "fixture", "CidrBlock": "10.0.0.0/16", "State": "available", "IsDefault": False}]}),
            (aws_tools.list_subnets, "describe_subnets", {"Subnets": [
                {"SubnetId": "fixture", "VpcId": "fixture", "CidrBlock": "10.0.0.0/24", "AvailabilityZone": "fixture", "State": "available"}]}),
            (aws_tools.list_acm_certificates, "list_certificates", {"CertificateSummaryList": [
                {"CertificateArn": "fixture", "DomainName": "example.invalid"}]}),
        ]
        with patch.object(aws_tools.boto3, "client") as factory:
            for function, method, response in cases:
                getattr(factory.return_value, method).return_value = response
                self.assertEqual(len(function("ap-southeast-2")), 1)
                self.assertEqual(factory.call_args.kwargs, {"region_name": "ap-southeast-2"})


if __name__ == "__main__":
    unittest.main()
