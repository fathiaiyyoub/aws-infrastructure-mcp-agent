variable "aws_region" {
  description = "AWS region for the development environment"
  type        = string
  default     = "ap-southeast-2"
}

variable "availability_zones" {
  description = "Availability Zones used by the development subnets"
  type        = list(string)
  default     = ["ap-southeast-2a", "ap-southeast-2b"]
}

variable "ami_id" {
  description = "Linux AMI ID valid for ap-southeast-2"
  type        = string
}

variable "instance_type" {
  description = "Low-cost EC2 instance type"
  type        = string
  default     = "t3.micro"
}
