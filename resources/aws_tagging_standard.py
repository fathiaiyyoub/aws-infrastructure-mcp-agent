"""
AWS resource tagging standard for learning and development infrastructure.
"""

REQUIRED_TAGS = {
    "ManagedBy": "Terraform",
    "Environment": "Development",
    "Project": "AI-Agents-Learning"
}

RULES = [
    "All supported AWS resources must include the required tags.",
    "Do not use the Environment value 'Production'.",
    "Resources created by this project should identify Terraform as the management mechanism."
]