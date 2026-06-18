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
