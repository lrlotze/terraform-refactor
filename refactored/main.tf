provider "aws" {
  region = "us-east-1"
}

# -------------------
# VPC (your network)
# -------------------

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

# -------------------
# Subnet (inside VPC)
# -------------------

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
}

# -------------------
# Internet Gateway
# -------------------

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
}

# -------------------
# EC2 (your server)
# -------------------

resource "aws_instance" "web" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t3.micro"

  subnet_id = aws_subnet.public.id
}
