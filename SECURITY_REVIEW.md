# Step 1 security and publication review

Review date: 9 October 2026 (Australia/Sydney).

Status: local preparation completed; owner review and explicit publication approval are required. No GitHub repository was created or modified, no push or commit was made, and no original Git history was rewritten. No AWS operation, OpenAI model request, or Terraform command was executed during this review.

## Confirmed findings and remediation

| Finding | Action / outcome |
|---|---|
| Complete MCP tool arguments were printed by the agent. | Replaced argument logging with tool-name metadata. Error paths omit raw diagnostics. |
| Configuration reader could read state and other files inside terraform/. | Restricted reads to top-level .tf and .tf.json configuration files; refused traversal, absolute paths, alternate streams, and linked/reparse targets. |
| Hard-linked configuration files could expose content outside terraform/. | Read/list validation now requires st_nlink == 1, with an opened-handle recheck before reading. A real external hard-link regression covers .tf and .tf.json. |
| Existing symlinks could redirect configuration writes. | Validate the target and use a temporary sibling file plus atomic replacement. Hard-link targets are not overwritten in place. |
| Direct MCP calls could execute a saved plan without the agent's human approval. | Execution now requires a one-use parent-process grant, bound to the operation and plan hash, expiring after 60 seconds. The agent creates it only after terminal approval; ordinary calls never forward an ambient grant. |
| SDK trace/logging could capture tool and model payloads. | Disabled tracing for the agent run and suppressed SDK model/tool diagnostic payload logging. |
| Provider/CLI output could contain secrets. | Shared best-effort redaction for outputs, configuration reads, and reports; unexpected MCP tool errors suppress raw details. Terraform execution failures now explicitly report failure instead of returning output that could be mistaken for success. |
| MCP's default subprocess environment does not include AWS environment configuration. | Explicitly forwards AWS settings and existing policy settings. Does not forward the OpenAI key or an ambient approval grant. |
| requirements.txt omitted OpenAI Agents SDK. | Added openai-agents==0.23.1 and tested it in isolation. Retained existing mcp==2.2.0, boto3==1.43.109, and PyYAML==6.0.3 versions. |
| .env.example was empty and ignore rules were incomplete. | Added placeholders and expanded exclusions for credentials, Terraform artifacts, environments, logs, reports, caches, and build output. |
| Provider lock file was ignored. | Removed that exclusion; the existing .terraform.lock.hcl is in the publication manifest. |
| No substantive regression tests were present. | Added focused security, agent, AWS-mock, publication, and real local MCP tests. |

All 15 existing MCP tools, all three resources, and all three prompts remain registered. The complete agent and AWS/Terraform capabilities remain in the candidate. The existing cost-estimation Markdown prompt and its pricing/reporting rules were not edited. No desktop, screenshots, packaging, installer, or cloud service was added.

## Credential and artifact audit

No known real OpenAI key, AWS access/secret/session key, GitHub token, password, private key, certificate, or credential-bearing connection string was found in the publication candidate. No credential rotation is presently indicated by these findings. This is not a guarantee that every possible secret format has been detected.

The offline scanner checks known key/token signatures, private keys/certificates, JWTs, authentication headers, credential URLs, credential-like literals/environment assignments, account identifiers, and personal machine paths. It reports file/line/rule only, never matched values. Manual review covered all project-owned source, prompts, policy/configuration, Terraform source/lock file, examples, and documentation. Synthetic test data was reviewed and is not a real credential.

Gitleaks 8.30.1 was downloaded to a temporary directory outside the publication candidate from the official gitleaks/gitleaks GitHub release. Its archive SHA-256 matched the published checksums and GitHub asset digest; the executable was rechecked against that archive for the final audit. The final candidate scan found zero findings across the exact 36 manifest files, agreeing with tools/audit_publication.py.

The earlier separate working-tree scan inventoried 17,058 files and scanned approximately 372.69 MB, including ignored local artifacts and both virtual environments, with global path exclusions removed in a temporary rules copy. It flagged 248 matches in 48 dependency files. All 48 files matched published package artifacts byte-for-byte; the matches were SDK examples, schema/type names, constants, and documentation JWTs. All 248 were classified as false positives; no project credentials or unresolved findings were found. That full-tree result is from the independent scan; the final audit reran the exact publication candidate.

Scanning stayed local, with redacted reports outside the candidate. Gitleaks skips recognised binary contents; archive depth was 3 and decoding depth 5. No local history was available. No full dependency vulnerability audit was performed. Pattern scanning cannot prove that all possible secrets are absent. GitHub secret scanning/push protection remain supplementary safeguards.

Confirmed sensitive local artifacts, preserved and excluded:

- terraform/terraform.tfstate: 181 bytes, no resources in the inspected JSON.
- terraform/terraform.tfstate.backup: 3,079 bytes, an S3 resource and AWS account identifier at line 79. The identifier is not reproduced.
- .venv/pyvenv.cfg: local machine paths. The entire original environment remains excluded and unchanged.
- .security-review/: temporary isolated test dependencies, review index, test output, and candidate fingerprints. Excluded in its entirety.
- Generated Python bytecode/cache directories: excluded.

No local state or credential file was deleted, and no AWS profiles outside the project were read, changed, or copied. State and backup were inspected locally for credential patterns without displaying their contents. Other state/plan/variable-value files, logs, private credentials, generated reports, and build artifacts are prohibited by the manifest check and ignore rules.

If a credential is discovered later, remove it from publishable files, determine whether it reached history/remotes, and rotate or revoke it through the owner. Do not assume deletion or history cleanup invalidates it. See [GitHub's remediation guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Remaining risks and decisions for review

1. **Sample SSH ingress remains open to 0.0.0.0/0.** No Terraform configuration was changed because this may describe an existing deployment. Before deploying, replace it with a validated administrator CIDR (preferably /32), or remove SSH ingress. The owner should decide whether to publish the explicitly warned sample unchanged or authorise a configuration change first.
2. **Local trust boundary.** The per-call grant blocks an ordinary MCP tool call from bypassing approval. A host owner or process with equivalent access can construct a grant, edit code, or execute Terraform directly. This is not remote authentication or an OS sandbox. The digest checks plan identity, not human consent. Grant consumption prevents replay within one server process; a host-controlled process can reinject a grant into another process.
3. **Concurrency and untrusted inputs.** Concurrent local mutation between checks and use is outside this small application's protection. Use a trusted project directory and one operator. Terraform providers, provisioners, external data sources, credential_process profiles, and selected executable paths must be trusted. Validation/planning are not sandboxes. Configuration writes and planning do not require the apply/destroy approval gate.
4. **Policy context is not enforcement.** Budget, development-only, production restrictions, and tagging policy text are not independent runtime authorisation. IAM permissions and operator review remain essential.
5. **Data exposure.** Redaction is best effort and can hide relevant values or miss unfamiliar secret formats. Avoid secrets in configuration. Model requests send configuration/tool context to OpenAI; generated reports and terminal output require review before sharing. Tracing is disabled, but this is not an offline or zero-data-transfer application.
6. **Functional limits.** Cost arithmetic/pricing is model-driven, not deterministic billing calculation. Several discovery tools are fixed to Sydney. AWS list operations retain their existing pagination limitations. The main entry point retains its fixed cost-estimation request.
7. **Dependency limits.** Direct versions are pinned; transitive dependencies are not fully locked. No full supply-chain/CVE audit was performed. The original virtual environment could not run here because its referenced interpreter was inaccessible; a separate environment was used instead.
8. **Publication choices.** Explicit owner approval, target GitHub owner/repository, and any desired licence remain to be supplied. No remote was probed or configured.

## Change summary

Modified:

- .gitignore
- .env.example
- README.md
- requirements.txt
- agent/agent.py
- mcp_client/client.py
- mcp_server/server.py
- mcp_server/terraform_tools.py

Created:

- security.py
- tests/test_security.py
- tests/test_mcp.py
- tests/test_publication.py
- tools/audit_publication.py
- SECURITY_REVIEW.md
- PUBLICATION_MANIFEST.txt

Existing AWS discovery code, all prompts/resources, Terraform configurations, and package initialisers are retained. The provider lock file is newly eligible for Git. No legitimate source is excluded to narrow the agent's capabilities.

Behaviour changes are limited to stricter file access, atomic configuration writes, safer logging/output/error handling, tracing suppression, explicit AWS environment forwarding, and per-call approval enforcement. Direct MCP clients that previously invoked apply/destroy without the agent gate must now use the trusted reviewed approval path. Configuration reads no longer return state, tfvars, nested files, or hard-linked configuration content. Listing omits hard-linked configurations; atomic writes retain their existing behaviour. A report may redact credential-like text.

## Test report

Python 3.12.14, Windows, separate ignored test environment; no changes to the user's original virtual environment.

- Full unittest suite: **33 tests run; 32 passed, 1 skipped, 0 failures/errors**.
- Native file-symlink test skipped because the host denied symlink creation. Mocked reparse rejection, real external hard-link read rejection for .tf and .tf.json, and hard-link/atomic-write tests passed. Actual Windows junction handling was not exercised.
- Real MCP stdio: all 15 tools registered with the agent, all resources/prompts discovered, cost prompt retrieved, state reads denied, direct unapproved apply/destroy denied.
- Mocked Terraform: validation/planning commands, normal/destroy plans, missing/modified plans, plan mutation during display, approval rejection, operation/hash/expiry binding, one-use consumption, authorised execution, safe failures.
- AWS discovery used Boto3 mocks. Runtime AWS environment credential loading and OpenAI SDK environment key loading used synthetic credentials without API calls.
- Existing cost request and report output exercised with Runner mocked; tracing settings verified.
- Dependency check: no broken requirements. All application modules imported successfully.
- Final publication scans: tools/audit_publication.py and Gitleaks 8.30.1 both checked all 36 manifest files with zero findings, including the hard-link fix and updated documentation. Exact candidate index paths and bytes were compared with the working tree; excluded artifacts were checked separately.

Earlier test-only environment/assertion failures were corrected before the passing run: preserving Windows SSL setup and matching MCP's intentionally generic error response. No live AWS, OpenAI pricing/model, or actual Terraform execution was verified. Those require separate authorisation and are not claimed as successful.

Reproduce with:

~~~powershell
python -m pip install -r requirements.txt
python -m pip check
python -m unittest discover -s tests -v
python tools/audit_publication.py
~~~

## Git and publication manifest

No pre-existing Git metadata was found in the project or its inspected ancestor directories. There was no local tracked-file/branch/tag/history inventory to scan. Any separate prior repository or remote must be inspected before reusing its history; none is assumed clean.

An isolated, uncommitted Git review index under .security-review/ was used to verify actual Git exclusions and the exact candidate. It is not a remote repository and is itself excluded. The project root was not initialised as a Git repository. No original history was created, deleted, or rewritten.

PUBLICATION_MANIFEST.txt lists exactly 36 proposed files, including the full application, safe Terraform source/lock file, prompts/resources, dependencies, credential template, tests, audit helper, and documentation. No Terraform state, saved plans, private credentials, sensitive logs, generated reports, environments, or executables are included.

After owner approval, initialise a clean root repository if appropriate, stage only the manifest paths, compare the staged paths and bytes against the reviewed candidate, rerun scanning, then commit. Review any newly discovered original history before proceeding. Create/configure/push a remote only after the owner explicitly approves the final candidate and destination. Do not use a blanket force-push or rewrite history.

Terraform state/plan sensitivity and provider lock-file handling follow [HashiCorp sensitive-data guidance](https://developer.hashicorp.com/terraform/language/manage-sensitive-data) and [lock-file guidance](https://developer.hashicorp.com/terraform/language/files/dependency-lock).
