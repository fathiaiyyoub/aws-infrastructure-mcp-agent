"""Small shared controls for trusted, local execution; not an OS sandbox."""
import functools
import hmac
import json
import os
import re
import time

APPROVAL_ENV = "INFRA_AGENT_APPROVAL"
SECRET_ENV_NAMES = (
    "OPENAI_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "GITHUB_TOKEN", "GH_TOKEN",
)


class SafeToolError(RuntimeError):
    """An application-authored error safe to return through MCP."""


def redact_text(text: str) -> str:
    """Best-effort output protection, not a substitute for secret-free inputs."""
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name, "")
        if len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    patterns = (
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        r"\bsk-[A-Za-z0-9_-]{16,}\b",
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
        r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+)?PRIVATE KEY-----",
        r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9_./+=-]+",
        r"(?i)(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s/@:]+:[^\s/@]+@",
    )
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    text = re.sub(
        r'''(?im)(["']?(?:[\w-]*(?:password|secret|token|api_key|access_key|authorization)[\w-]*)["']?\s*[:=]\s*)("[^"\r\n]*"|'[^'\r\n]*'|[^\s,}\r\n]+)''',
        r'\1"[REDACTED]"', text,
    )
    return text


def redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if re.search(
            r"(?i)password|secret|token|api_key|access_key|authorization", str(key)
        ) else redact_value(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


def safe_tool_result(function):
    """Retain tool signatures, redact output, and suppress raw provider errors."""
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return redact_value(function(*args, **kwargs))
        except SafeToolError as exc:
            raise SafeToolError(redact_text(str(exc))) from None
        except Exception:
            raise SafeToolError(
                "Tool failed. Check local credentials, inputs and prerequisites; "
                "raw error details are withheld to protect sensitive data."
            ) from None
    return wrapped


def make_approval_grant(operation: str, digest: str) -> str:
    """Called by trusted client code only after terminal approval."""
    if operation not in ("apply", "destroy") or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SafeToolError("Invalid Terraform approval request.")
    return json.dumps({"operation": operation, "sha256": digest, "expires": time.time() + 60})


def require_terraform_approval(operation: str, digest: str) -> None:
    """Consume a one-call parent-process grant, bound to operation and plan.

    MCP callers cannot supply this through tool arguments. A user who controls
    the host/process environment can create a grant: this is a local application
    boundary, not authentication against that same user.
    """
    raw = os.environ.pop(APPROVAL_ENV, "")
    try:
        grant = json.loads(raw)
        valid = (
            grant["operation"] == operation
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
            and hmac.compare_digest(grant["sha256"], digest)
            and time.time() <= float(grant["expires"]) <= time.time() + 61
        )
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        raise SafeToolError("Terraform execution requires a fresh terminal-approved operation and plan.")
