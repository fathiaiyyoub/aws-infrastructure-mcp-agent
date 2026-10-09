output "vpc_id" {
  value = aws_vpc.development.id
}

output "subnet_ids" {
  value = aws_subnet.development[*].id
}

output "instance_ids" {
  value = aws_instance.development[*].id
}
