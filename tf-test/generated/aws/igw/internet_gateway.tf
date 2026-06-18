resource "aws_internet_gateway" "tfer--igw-08b3758623655a0a4" {
  region = "us-east-1"
  vpc_id = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}

resource "aws_internet_gateway" "tfer--igw-0eaf698dea923f44f" {
  region = "us-east-1"
  vpc_id = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0b530d7af19ffa635_id}"
}
