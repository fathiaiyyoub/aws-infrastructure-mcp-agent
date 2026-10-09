resource "aws_instance" "development" {
  count         = 3
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = aws_subnet.development[count.index % 2].id

  vpc_security_group_ids = [aws_security_group.ec2.id]

  root_block_device {
    encrypted = true
  }

  tags = {
    Name = "development-ec2-${count.index + 1}"
  }
}
