import os


def get_deployment_environment() -> dict:
    """
    Return the deployment environment available to the AI agent.

    Values can be overridden through environment variables so the
    resource reflects the application's actual runtime environment.
    """

    return {
        "environment": os.getenv("DEPLOYMENT_ENV", "development"),
        "aws_region": os.getenv("AWS_REGION", "ap-southeast-2"),
        "monthly_budget_usd": float(
            os.getenv("MONTHLY_BUDGET_USD", "20")
        ),
        "production_allowed": (
            os.getenv("PRODUCTION_ALLOWED", "false").lower() == "true"
        ),
    }