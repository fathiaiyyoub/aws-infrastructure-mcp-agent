resource "aws_vpc" "development" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "development-vpc" }
}

resource "aws_internet_gateway" "development" {
  vpc_id = aws_vpc.development.id
  tags   = { Name = "development-igw" }
}

resource "aws_subnet" "development" {
  count                   = 2
  vpc_id                  = aws_vpc.development.id
  cidr_block              = cidrsubnet(aws_vpc.development.cidr_block, 8, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "development-subnet-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.development.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.development.id
  }
  tags = { Name = "development-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.development[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "ec2" {
  name        = "development-ec2-sg"
  description = "Restricted development EC2 access"
  vpc_id      = aws_vpc.development.id

  ingress {
    description = "SSH from approved administrator network"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "development-ec2-sg" }
}
