import boto3


def list_ec2_instances(region: str) -> list[dict]:

    ec2 = boto3.client(
        "ec2",
        region_name=region
    )

    response = ec2.describe_instances()

    instances = []

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append({
                "instance_id": instance["InstanceId"],
                "state": instance["State"]["Name"],
                "instance_type": instance["InstanceType"]
            })

    return instances


def list_vpcs(region: str) -> list[dict]:

    ec2 = boto3.client(
        "ec2",
        region_name=region
    )

    response = ec2.describe_vpcs()

    vpcs = []

    for vpc in response["Vpcs"]:
        vpcs.append({
            "vpc_id": vpc["VpcId"],
            "cidr_block": vpc["CidrBlock"],
            "state": vpc["State"],
            "is_default": vpc["IsDefault"]
        })

    return vpcs

def list_subnets(region: str) -> list[dict]:

    ec2 = boto3.client(
        "ec2",
        region_name=region
    )

    response = ec2.describe_subnets()

    subnets = []

    for subnet in response["Subnets"]:
        subnets.append({
            "subnet_id": subnet["SubnetId"],
            "vpc_id": subnet["VpcId"],
            "cidr_block": subnet["CidrBlock"],
            "availability_zone": subnet["AvailabilityZone"],
            "state": subnet["State"]
        })

    return subnets

def list_acm_certificates(region: str) -> list[dict]:

    acm = boto3.client(
        "acm",
        region_name=region
    )

    response = acm.list_certificates()

    certificates = []

    for cert in response["CertificateSummaryList"]:
        certificates.append({
            "certificate_arn": cert["CertificateArn"],
            "domain_name": cert["DomainName"],
            "status": cert.get("Status", "Unknown")
        })

    return certificates

if __name__ == "__main__":

    instances = list_ec2_instances("ap-southeast-2")
    vpcs = list_vpcs("ap-southeast-2")
    subnets = list_subnets("ap-southeast-2")
    certificates = list_acm_certificates("us-east-1")
    certificates = list_acm_certificates("ap-northeast-1")

    # print("EC2 instances:")

    for instance in instances:
        # print(instance)
        pass  # Keep the loop valid while its console output is commented out.

    # print("\nVPCs:")

    for vpc in vpcs:
        # print(vpc)
        pass  # Keep the loop valid while its console output is commented out.

    # print("\nSubnets:")

    for subnet in subnets:
        # print(subnet)
        pass  # Keep the loop valid while its console output is commented out.

    for cert in certificates:
        # print(cert)
        pass  # Keep the loop valid while its console output is commented out.
