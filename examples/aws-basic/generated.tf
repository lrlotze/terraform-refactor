resource "aws_instance" "tfer--i-0353d2dea60f9c1e1_" {
  ami                         = "ami-0c02fb55956c7d316"
  associate_public_ip_address = "true"
  availability_zone           = "us-east-1b"

  capacity_reservation_specification {
    capacity_reservation_preference = "open"
  }

  cpu_options {
    core_count       = "1"
    threads_per_core = "2"
  }

  credit_specification {
    cpu_credits = "unlimited"
  }

  disable_api_stop        = "false"
  disable_api_termination = "false"
  ebs_optimized           = "false"

  enclave_options {
    enabled = "false"
  }

  get_password_data                    = "false"
  hibernation                          = "false"
  instance_initiated_shutdown_behavior = "stop"
  instance_type                        = "t3.micro"
  ipv6_address_count                   = "0"

  maintenance_options {
    auto_recovery = "default"
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_protocol_ipv6          = "disabled"
    http_put_response_hop_limit = "1"
    http_tokens                 = "optional"
    instance_metadata_tags      = "disabled"
  }

  monitoring                 = "false"
  placement_partition_number = "0"

  primary_network_interface {
    network_interface_id = "eni-0a95b3b87c0886ae9"
  }

  private_dns_name_options {
    enable_resource_name_dns_a_record    = "false"
    enable_resource_name_dns_aaaa_record = "false"
    hostname_type                        = "ip-name"
  }

  private_ip = "10.0.1.208"
  region     = "us-east-1"

  root_block_device {
    delete_on_termination = "true"
    encrypted             = "false"
    volume_size           = "8"
    volume_type           = "gp2"
  }

  source_dest_check      = "true"
  subnet_id              = "${data.terraform_remote_state.subnet.outputs.aws_subnet_tfer--subnet-07e44e47643c99518_id}"
  tenancy                = "default"
  vpc_security_group_ids = ["sg-0a7a91f52be219bee"]
}
resource "aws_internet_gateway" "tfer--igw-08b3758623655a0a4" {
  region = "us-east-1"
  vpc_id = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_internet_gateway" "tfer--igw-0eaf698dea923f44f" {
  region = "us-east-1"
  vpc_id = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0b530d7af19ffa635_id}"
}
resource "aws_subnet" "tfer--subnet-01a84979be17b1c4e" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.32.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_subnet" "tfer--subnet-02553d65232c646ec" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.0.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_subnet" "tfer--subnet-07e44e47643c99518" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "10.0.1.0/24"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0b530d7af19ffa635_id}"
}

resource "aws_subnet" "tfer--subnet-08813ee742f076555" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.48.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_subnet" "tfer--subnet-0a8e9c13f0907cf75" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.80.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_subnet" "tfer--subnet-0a9ead7049f1bae6c" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.64.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_subnet" "tfer--subnet-0d3a5168ece873627" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.16.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id                                         = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}
resource "aws_vpc" "tfer--vpc-0b530d7af19ffa635" {
  assign_generated_ipv6_cidr_block     = "false"
  cidr_block                           = "10.0.0.0/16"
  enable_dns_hostnames                 = "false"
  enable_dns_support                   = "true"
  enable_network_address_usage_metrics = "false"
  instance_tenancy                     = "default"
  ipv6_netmask_length                  = "0"
  region                               = "us-east-1"
}

resource "aws_vpc" "tfer--vpc-0d6abae348aa13541" {
  assign_generated_ipv6_cidr_block     = "false"
  cidr_block                           = "172.31.0.0/16"
  enable_dns_hostnames                 = "true"
  enable_dns_support                   = "true"
  enable_network_address_usage_metrics = "false"
  instance_tenancy                     = "default"
  ipv6_netmask_length                  = "0"
  region                               = "us-east-1"
}
