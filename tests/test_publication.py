import unittest
from tools.audit_publication import prohibited, scan_text


class PublicationChecks(unittest.TestCase):
    def test_scanner_detects_synthetic_secrets_without_returning_values(self):
        value = "sk-" + "z" * 32
        findings = scan_text(value)
        self.assertTrue(findings)
        self.assertNotIn(value, repr(findings))
        self.assertTrue(scan_text('password' + '=' + chr(34) + 'nonpublic-value' + chr(34)))
        self.assertTrue(scan_text("AWS_SESSION_TOKEN=nonpublic-value"))
        self.assertTrue(scan_text("https://user:" + "nonpublic@example.org"))

    def test_placeholder_template_is_allowed(self):
        self.assertFalse(scan_text("OPENAI_API_KEY=replace-with-your-own-key"))

    def test_sensitive_artifacts_are_prohibited(self):
        for file in ("terraform/terraform.tfstate.backup", "terraform/tfplan", ".env",
                     ".aws/credentials", "local.tfvars", "reports/report.md", ".security-review/test.log"):
            self.assertTrue(prohibited(file), file)
        for file in (".env.example", "terraform/.terraform.lock.hcl", "mcp_server/aws_tools.py"):
            self.assertFalse(prohibited(file), file)
