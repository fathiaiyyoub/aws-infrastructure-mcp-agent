# AWS Infrastructure MCP Agent

A local Python portfolio project for inspecting and managing Terraform-defined AWS infrastructure with an AI agent. It helps developers review proposed infrastructure, estimate operating costs, discover AWS resources, and require human review before applying a saved Terraform plan.

This repository contains the complete agent, MCP client/server, AWS tools, Terraform tools, prompts, and policies. It is a development demonstration, not a production-ready infrastructure control plane.

## Architecture and capabilities

The OpenAI Agents SDK orchestrates tools through a local stdio MCP client. The client starts the MCP server using the same Python interpreter and the project root as its working directory.

- Terraform tools inspect/write configuration, validate it, create normal or destroy plans, and execute an approved saved plan.
- Boto3 tools discover EC2 instances, VPCs, subnets, and ACM certificates through the developer's own AWS credentials.
- MCP resources supply deployment policy, tagging standards, and environment context.
- MCP prompts support security review, resilience review, and AWS cost estimation.
- The existing cost prompt uses model reasoning and web search for pricing evidence, usage assumptions, partial totals, and limitations. It is not an AWS billing calculator; arithmetic and source accuracy require review.

Entry points are agent/agent.py, mcp_client/client.py, and mcp_server/server.py. Terraform tools operate on this repository's terraform/ directory.

## Developer setup

Use Python 3.12 (offline tests were run with 3.12.14). The previous local environment referenced Python 3.13, but that interpreter was inaccessible during this review. Use a fresh virtual environment; do not copy another developer's environment.

From the project root in PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
~~~

Direct dependency versions are pinned. Transitive dependencies are not fully locked. The existing MCP, Boto3, and PyYAML versions were retained; the previously missing OpenAI Agents SDK dependency was added and tested locally.

Set your OpenAI key in the current process without entering its value in shell history:

~~~powershell
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenAI API key' -AsSecureString)).Password
~~~

The SDK reads OPENAI_API_KEY at runtime. Never put its value in source, screenshots, or committed files. .env.example is a reference template only; this application does not automatically load .env files. See the [official OpenAI setup guide](https://developers.openai.com/api/docs/quickstart).

For AWS discovery and Terraform operations, configure your own credentials outside the project using the standard AWS provider chain: for example, an existing AWS profile, temporary environment credentials, or an appropriate role. Prefer short-lived credentials. Do not copy AWS credential files into this repository.

~~~powershell
$env:AWS_PROFILE = 'your-development-profile'
$env:AWS_REGION = 'ap-southeast-2'
~~~

The MCP client forwards AWS environment settings to its subprocess. OpenAI credentials are not forwarded. Several existing discovery tools use Sydney explicitly; changing AWS_REGION alone does not change those tools. Terraform uses var.aws_region.

Terraform operations require a separately installed Terraform CLI (configuration requires >=1.5.0), reviewed configuration, your own AWS permissions, a region-appropriate ami_id, and provider initialisation. Initialisation downloads provider code; perform it manually only for configurations you trust. The included provider lock file records the existing provider selection. No Terraform command is required for the offline test suite.

**Review the sample before any deployment:** its SSH ingress currently allows 0.0.0.0/0. This was preserved to avoid an unreviewed change to an existing deployment. Restrict it to your administrator network, preferably a specific /32, or remove SSH ingress if using another access method. Do not apply the sample as-is.

## Running the existing application

~~~powershell
# Starts its own MCP subprocess; makes paid OpenAI/web-search requests.
python -m agent.agent

# Standalone MCP stdio server; waits for protocol input.
python -m mcp_server.server

# Local prompt-retrieval demonstration; no model or AWS request.
python -m mcp_client.client
~~~

The current agent entry point contains a fixed cost-estimation request in Runner.run(). It is not an interactive chat shell. Developers can change that request in local code to exercise the existing capabilities. All infrastructure tools remain present even during the cost demonstration; this full agent is not a cost-only execution sandbox.

## Approval and security boundaries

For apply/destroy, the agent creates an authoritative saved plan, displays the plan and diagnostics with credential redaction, then asks for terminal approval. Only yes after whitespace trimming authorises execution. Rejection performs no apply.

After approval, the trusted client starts a server subprocess with a one-use, short-lived grant bound to the operation and plan hash. The server consumes that grant and verifies the saved plan's SHA-256 before execution. Both apply and destroy execute the corresponding saved plan with terraform apply tfplan; destroy first creates a destroy plan. An ordinary direct MCP execution call without the grant is rejected.

Grant consumption prevents replay within that server process; it does not prevent a host-controlled process from reinjecting a grant into another process. The grant is not a remote authentication system. Someone who controls the host, source, or process environment can manufacture it or run Terraform directly. The hash detects a changed plan; it is not independent evidence of human consent. Keep this a trusted, local stdio application. Concurrent local processes must not change the configuration/plan during approval or execution.

Configuration readers allow top-level .tf and .tf.json files only; state, plans, .tfvars, symlinks/reparse targets, and hard-linked files are refused. Hard-link checks use the filesystem link count, including a recheck of the opened file before reading. Listing excludes hard-linked configurations. Writes retain atomic replacement so an existing hard-link target is not modified in place. Do not process untrusted Terraform: validation/planning can involve providers and planning may execute external data sources. File writes and planning do not use the apply/destroy approval gate.

Tool arguments are not logged. Tool outputs and final reports have best-effort credential redaction; unexpected provider errors omit raw details. SDK tracing is disabled for the agent run, and model/tool diagnostic payload logging is suppressed. This does not prevent sending configuration/tool results needed by the model to OpenAI. Redaction cannot recognise every possible secret: use secret-free configurations and review all output before sharing it.

Deployment environment, production restrictions, tagging rules, and budget resources are policy context, not independently enforced controls. AWS IAM permissions remain essential. OpenAI/web-search calls can incur API charges; infrastructure operations can incur AWS charges or delete resources.

## Safe verification and publication

~~~powershell
python -m unittest discover -s tests -v
python tools/audit_publication.py
~~~

Tests mock Terraform execution and AWS/model calls. Local MCP integration tests exercise actual stdio discovery, prompt/resource retrieval, and denial of unapproved execution. No live cloud or model verification is implied. Final local verification: 33 tests run, 32 passed, 1 skipped. The external hard-link read regression passed for both .tf and .tf.json. The native symlink test was skipped because Windows denied symlink creation; actual junction handling was not exercised. Both the publication scanner and Gitleaks 8.30.1 found zero findings in the final 36-file candidate.

Read [SECURITY_REVIEW.md](SECURITY_REVIEW.md) and the exact [publication manifest](PUBLICATION_MANIFEST.txt). Keep state, plans, variable values, credentials, environments, logs, and generated reports local. .gitignore cannot remove previously tracked files or historical secrets. Recheck staged contents and available history before any publication. Public GitHub publication requires the owner's explicit approval of the final candidate.
