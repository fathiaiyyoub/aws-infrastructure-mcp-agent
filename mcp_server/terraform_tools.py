import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from security import SafeToolError, redact_text, require_terraform_approval

TERRAFORM_DIR = Path(__file__).resolve().parent.parent / "terraform"


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(
            getattr(path.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
    except FileNotFoundError:
        return False


def _configuration_path(filename: str, *, for_read: bool = True) -> Path:
    # Reject traversal, Windows alternate streams, and device/absolute paths.
    if (not isinstance(filename, str) or not filename
            or any(char in filename for char in '/\\:\x00')
            or not filename.endswith((".tf", ".tf.json"))):
        raise SafeToolError("Only top-level .tf or .tf.json configuration files are allowed.")
    base = TERRAFORM_DIR.resolve()
    candidate = base / filename
    if _is_link(candidate) or candidate.resolve().parent != base:
        raise SafeToolError("Terraform configuration links and path escapes are not allowed.")
    if candidate.exists() and not candidate.is_file():
        raise SafeToolError("Terraform configuration must be a regular file.")
    # st_nlink is available on Windows/NTFS as well as POSIX filesystems.
    if for_read and candidate.exists() and candidate.stat().st_nlink != 1:
        raise SafeToolError("Hard-linked Terraform configuration files cannot be read.")
    return candidate


def _saved_plan_path() -> Path:
    candidate = TERRAFORM_DIR / "tfplan"
    if _is_link(candidate) or (candidate.exists() and (
            not candidate.is_file() or candidate.stat().st_nlink != 1)):
        raise SafeToolError("Saved Terraform plan must be a regular, unlinked local file.")
    return candidate


def validate_terraform() -> str:
    result = subprocess.run(
        ["terraform", "validate", "-no-color"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True,
    )
    return redact_text(result.stdout if result.returncode == 0 else result.stderr)


def plan_terraform() -> dict:
    plan_path = _saved_plan_path()
    plan_path.unlink(missing_ok=True)
    result = subprocess.run(
        ["terraform", "plan", "-no-color", "-input=false", "-out=tfplan"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        plan_path.unlink(missing_ok=True)
        raise SafeToolError("Terraform planning failed; raw output withheld.")
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    shown = subprocess.run(
        ["terraform", "show", "-no-color", "tfplan"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if shown.returncode != 0:
        raise SafeToolError("Terraform plan display failed; raw output withheld.")
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != digest:
        raise SafeToolError("Saved plan changed while it was being displayed. Plan again.")
    warning_start = result.stdout.find("Warning:")
    warnings = result.stdout[warning_start:] if warning_start >= 0 else ""
    return {
        "plan": redact_text(shown.stdout),
        "diagnostics": redact_text("\n".join(filter(None, [warnings, result.stderr, shown.stderr]))),
        "plan_sha256": digest,
    }


def write_terraform_file(filename: str, content: str) -> str:
    try:
        file_path = _configuration_path(filename, for_read=False)
    except SafeToolError as exc:
        return f"Rejected: {exc}"
    # Atomic replacement avoids following target symlinks or writing through
    # hard links. The directory itself must remain under trusted local control.
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=file_path.parent,
            prefix=".tf-write-", delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(content)
        _configuration_path(filename, for_read=False)
        os.replace(temp_name, file_path)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
    return f"Terraform file written: {filename}"


def read_terraform_file(filename: str) -> str:
    try:
        file_path = _configuration_path(filename)
    except SafeToolError as exc:
        return f"Access denied: {exc}"
    if not file_path.is_file():
        return "Terraform configuration file does not exist."
    with file_path.open("r", encoding="utf-8") as handle:
        # Recheck the opened file before reading any content.
        if os.fstat(handle.fileno()).st_nlink != 1:
            return "Access denied: Hard-linked Terraform configuration files cannot be read."
        return redact_text(handle.read())


def list_terraform_files() -> list[str]:
    names = []
    for file in TERRAFORM_DIR.iterdir():
        try:
            if _configuration_path(file.name).is_file():
                names.append(file.name)
        except SafeToolError:
            continue
    return sorted(names)


def apply_terraform(plan_sha256: str) -> str:
    require_terraform_approval("apply", plan_sha256)
    plan_path = _saved_plan_path()
    if not plan_path.is_file():
        raise SafeToolError("Saved Terraform plan is missing. Plan and approve again.")
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != plan_sha256:
        raise SafeToolError("Saved Terraform plan changed. Plan and approve again.")
    result = subprocess.run(
        ["terraform", "apply", "-no-color", "tfplan"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise SafeToolError("Terraform execution failed; raw output withheld. Re-plan before retrying.")
    return redact_text(result.stdout + result.stderr)


def destroy_terraform(plan_sha256: str) -> str:
    require_terraform_approval("destroy", plan_sha256)
    plan_path = _saved_plan_path()
    if not plan_path.is_file():
        raise SafeToolError("Saved Terraform plan is missing. Plan and approve again.")
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != plan_sha256:
        raise SafeToolError("Saved Terraform plan changed. Plan and approve again.")
    result = subprocess.run(
        ["terraform", "apply", "-no-color", "tfplan"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise SafeToolError("Terraform execution failed; raw output withheld. Re-plan before retrying.")
    return redact_text(result.stdout + result.stderr)


def plan_terraform_destroy() -> dict:
    plan_path = _saved_plan_path()
    plan_path.unlink(missing_ok=True)
    result = subprocess.run(
        ["terraform", "plan", "-no-color", "-input=false", "-destroy", "-out=tfplan"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        plan_path.unlink(missing_ok=True)
        raise SafeToolError("Terraform planning failed; raw output withheld.")
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    shown = subprocess.run(
        ["terraform", "show", "-no-color", "tfplan"],
        cwd=TERRAFORM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if shown.returncode != 0:
        raise SafeToolError("Terraform plan display failed; raw output withheld.")
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != digest:
        raise SafeToolError("Saved plan changed while it was being displayed. Plan again.")
    warning_start = result.stdout.find("Warning:")
    warnings = result.stdout[warning_start:] if warning_start >= 0 else ""
    return {
        "plan": redact_text(shown.stdout),
        "diagnostics": redact_text("\n".join(filter(None, [warnings, result.stderr, shown.stderr]))),
        "plan_sha256": digest,
    }
