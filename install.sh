#!/usr/bin/env bash
# terraform-refactor install script
#
# Usage:
#   git clone https://github.com/lucaslotze/terraform-refactor ~/tools/terraform-refactor
#   cd ~/tools/terraform-refactor
#   ./install.sh
#
# What it does:
#   1. Symlinks engine/ into ~/.bob/skills/tf-refactor-engine/engine
#   2. Writes ~/.bob/skills/tf-refactor/SKILL.md  (standalone refactor skill)
#   3. Writes ~/.bob/skills/aws-to-iac/SKILL.md   (full import + refactor skill)
#
# To update the engine later:
#   git pull          # picks up engine changes automatically via symlink
#   ./install.sh      # re-writes skill files if they changed

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOB_SKILLS_DIR="${HOME}/.bob/skills"
ENGINE_SKILL_DIR="${BOB_SKILLS_DIR}/tf-refactor-engine"
ENGINE_LINK="${ENGINE_SKILL_DIR}/engine"
ENGINE_SOURCE="${REPO_DIR}/engine"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

if [ ! -d "${ENGINE_SOURCE}" ]; then
  echo "ERROR: engine/ directory not found in ${REPO_DIR}"
  echo "       Make sure you are running this script from inside the cloned repo."
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "WARNING: python3 not found — the engine requires Python 3.8+"
fi

# ---------------------------------------------------------------------------
# Step 1 — Symlink engine into ~/.bob/skills/tf-refactor-engine/engine
# ---------------------------------------------------------------------------

mkdir -p "${ENGINE_SKILL_DIR}"

if [ -L "${ENGINE_LINK}" ]; then
  # Already a symlink — update it in case repo moved
  rm "${ENGINE_LINK}"
fi

ln -s "${ENGINE_SOURCE}" "${ENGINE_LINK}"
echo "✓ Engine symlinked: ${ENGINE_LINK} → ${ENGINE_SOURCE}"

# ---------------------------------------------------------------------------
# Step 2 — Write ~/.bob/skills/tf-refactor/SKILL.md
# ---------------------------------------------------------------------------

mkdir -p "${BOB_SKILLS_DIR}/tf-refactor"
cat > "${BOB_SKILLS_DIR}/tf-refactor/SKILL.md" << 'SKILL_EOF'
---
name: tf-refactor
description: Use when the user wants to refactor, clean up, or convert a Terraform file — including phrases like "refactor my generated.tf", "clean up this terraform", "convert terraformer output", or "make my tf file production ready".
---

# Terraform Refactor Skill

This skill runs the terraform-refactor engine against a Terraformer-generated `.tf` file and
produces clean, modular, production-ready Terraform output.

## Step 1 — Find or build the input file

Check the environment in this order:

**A. Active file** — if the user has a `.tf` file open, ask if that's the one to refactor.

**B. Existing `generated.tf`** — search for one with `glob` pattern `**/generated.tf`. If found, use it.

**C. Terraformer split output** — if neither A nor B applies, look for a Terraformer-style directory
tree: a folder containing multiple subdirectories each with their own `.tf` files (the classic
`generated/aws/vpc/vpc.tf`, `generated/aws/subnet/subnet.tf` layout). Detect with:
```
glob pattern: "**/aws/**/*.tf"
```

If a split Terraformer tree is found and no combined `generated.tf` exists, **build it automatically**:

```bash
find <generated_aws_dir> -name "*.tf" \
  -not -name "variables.tf" -not -name "outputs.tf" -not -name "provider.tf" \
  | sort | xargs cat > generated.tf
```

Exclude `variables.tf`, `outputs.tf`, and `provider.tf` — they contain boilerplate the engine's
noise-removal pass already handles. Only merge the primary resource files (`vpc.tf`, `subnet.tf`, etc.).

Tell the user: *"No generated.tf found — built one by merging the Terraformer output files."*

**D. Ask** — if none of the above, use `ask_followup_question` to ask the user which file or folder to use.

Do NOT proceed without a confirmed input file path.

## Step 2 — Confirm the state directory (optional but recommended)

The `--state-dir` flag merges Terraformer per-module state files so `terraform plan` works immediately.

- Check for a `generated/aws/` directory alongside the input file
- Check for any directory containing multiple `terraform.tfstate` files

If found, use it automatically and tell the user. If not found, proceed without it and note they
can run `terraform import` manually later.

## Step 3 — Determine the output directory

Default: create an `output/` directory next to the input file.
If the user specified a different location, use that.

## Step 4 — Locate the refactor engine

Look in this order:

1. Workspace: `find . -name "main.py" -path "*/engine/*" 2>/dev/null | head -1`
2. Installed:  `~/.bob/skills/tf-refactor-engine/engine/main.py`

```bash
ENGINE=$(find . -name "main.py" -path "*/engine/*" 2>/dev/null | head -1)
[ -z "$ENGINE" ] && ENGINE="${HOME}/.bob/skills/tf-refactor-engine/engine/main.py"
```

If neither exists, tell the user:

> The terraform-refactor engine is not installed. Run:
>
> ```bash
> git clone https://github.com/lucaslotze/terraform-refactor ~/tools/terraform-refactor
> cd ~/tools/terraform-refactor && ./install.sh
> ```

## Step 5 — Run the pipeline

```bash
python3 <engine_path> <input_file> <output_dir> [--state-dir <state_dir>]
```

Show the full output to the user so they can see exactly what was removed and grouped.

## Step 6 — Run terraform fmt on the output

```bash
terraform fmt <output_dir>
```

If `terraform` is not installed, skip this step and note it.

## Step 7 — Report results

Summarise clearly:

- How many resource blocks were in the input
- How many attributes were stripped (defaults removed)
- What output files were created and what each contains
- Whether a `terraform.tfstate` was generated

Then show the user the exact commands to verify:

```bash
cd <output_dir>
terraform init
terraform plan   # should show: No changes.
```

## Step 8 — Run the test suite (if available)

If `tests/test_pipeline.py` exists in the workspace, offer to run it:

```bash
python3 tests/test_pipeline.py
```

Report pass/fail count.

## Notes

- Never edit the input file — the engine only reads it
- If the engine errors, read the error, diagnose the cause (likely a parsing edge case), and report it clearly
- The output directory is safe to re-run into — files are overwritten each time
- `provider.tf` is not written by the engine — the user must create their own with the correct
  region and version constraints before running `terraform plan`
SKILL_EOF

echo "✓ Skill written:    ${BOB_SKILLS_DIR}/tf-refactor/SKILL.md"

# ---------------------------------------------------------------------------
# Step 3 — Write ~/.bob/skills/aws-to-iac/SKILL.md
# ---------------------------------------------------------------------------

mkdir -p "${BOB_SKILLS_DIR}/aws-to-iac"
cat > "${BOB_SKILLS_DIR}/aws-to-iac/SKILL.md" << 'SKILL_EOF'
---
name: aws-to-iac
description: Use when the user wants to convert, import, or export their AWS infrastructure to Terraform — including phrases like "convert my AWS to Terraform", "import my AWS infrastructure", "generate Terraform from my AWS account", or "turn my AWS resources into IaC".
---

# AWS to IaC Skill

This skill runs Terraformer against live AWS infrastructure, then pipes the output through the
terraform-refactor engine to produce clean, production-ready Terraform IaC.

## Step 1 — Check prerequisites

### 1a. Terraformer binary

```bash
which terraformer
```

If not found, print installation instructions and stop:

```
Terraformer is not installed. Install it with:

  # macOS
  brew install terraformer

  # Linux
  PROVIDER=aws
  VERSION=$(curl -s https://api.github.com/repos/GoogleCloudPlatform/terraformer/releases/latest \
    | grep tag_name | cut -d '"' -f4)
  curl -LO "https://github.com/GoogleCloudPlatform/terraformer/releases/download/${VERSION}/terraformer-${PROVIDER}-linux-amd64"
  chmod +x terraformer-${PROVIDER}-linux-amd64
  sudo mv terraformer-${PROVIDER}-linux-amd64 /usr/local/bin/terraformer

  # Windows (scoop)
  scoop install terraformer

Then re-run this skill.
```

### 1b. Fetch the supported resource list from the installed binary

**Always** run this before presenting resource options to the user — do not rely on a hardcoded list:

```bash
terraformer import aws list 2>&1
```

Store the output as the authoritative set of valid resource names for this run.

### 1c. AWS credentials

```bash
aws sts get-caller-identity 2>&1
```

- If it succeeds, note the account ID and region to the user and continue.
- If it fails, ask the user:
  - Do they have a named AWS profile to use? (`AWS_PROFILE=<name>`)
  - What region should be targeted?
  - Set `AWS_PROFILE` and `AWS_DEFAULT_REGION` accordingly before proceeding.

### 1d. Terraform CLI (needed for fmt + plan later)

```bash
which terraform
```

Note if missing — the refactor will still run but `terraform fmt` and `terraform plan` will be skipped.

## Step 2 — Confirm region and resource types

Using the resource list retrieved in Step 1b, propose these defaults (verify each name exists in
the live list before including it):

```
vpc, subnet, igw, ec2_instance, sg, route_table
```

Tell the user the proposed list and use `ask_followup_question` to confirm or adjust.
Rebuild the final list from the confirmed names and show it before continuing.

**Common resource names** (all verified against v0.8.x):
`vpc`, `subnet`, `igw`, `ec2_instance`, `sg`, `route_table`, `eip`, `nat`, `s3`, `iam`,
`route53`, `elb`, `alb`, `rds`, `elasticache`, `sns`, `cloudwatch`, `secretsmanager`, `ssm`,
`lambda`, `eks`, `ecs`, `ebs`, `kms`, `acm`, `cloudfront`, `dynamodb`, `sqs`, `kinesis`

## Step 3 — Determine output location

Defaults:
- Terraformer output: `./generated`
- Final clean IaC:    `./output`

If the user specifies a different location, use that.

## Step 4 — Bootstrap the AWS provider plugin

Terraformer requires the AWS provider binary to be present before it can run.
**Always do this step**, not only on error:

```bash
mkdir -p <generated_dir>
cat > <generated_dir>/versions.tf << 'EOF'
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "<region>"
}
EOF
cd <generated_dir> && terraform init -upgrade && cd -
```

## Step 5 — Run Terraformer

```bash
terraformer import aws \
  --resources=<comma-separated-resource-list> \
  --regions=<region> \
  --path-output=<generated_dir>
```

**Important:** use `--path-output`, not `--output`. The `--output` flag does not exist and will
cause a silent failure or "unknown output format" error.

Show the full output. If it errors:
- `NoCredentialProviders` — credentials not set, go back to Step 1c
- `AccessDeniedException` — IAM permissions missing; tell the user which policy is needed
- `<resource> not supported service` — the resource name is wrong for this Terraformer build;
  re-run `terraformer import aws list` and pick the correct name
- `unknown output format` — you used `--output` instead of `--path-output`; fix the flag and retry

## Step 6 — Locate the refactor engine

Look in this order:

1. Workspace: `find . -name "main.py" -path "*/engine/*" 2>/dev/null | head -1`
2. Installed:  `~/.bob/skills/tf-refactor-engine/engine/main.py`

```bash
ENGINE=$(find . -name "main.py" -path "*/engine/*" 2>/dev/null | head -1)
[ -z "$ENGINE" ] && ENGINE="${HOME}/.bob/skills/tf-refactor-engine/engine/main.py"
```

If neither exists, tell the user:

> The terraform-refactor engine is not installed. Run:
>
> ```bash
> git clone https://github.com/lucaslotze/terraform-refactor ~/tools/terraform-refactor
> cd ~/tools/terraform-refactor && ./install.sh
> ```

## Step 7 — Merge and refactor

### 7a. Build the merged input file

```bash
find <generated_dir>/aws -name "*.tf" \
  -not -name "variables.tf" \
  -not -name "outputs.tf" \
  -not -name "provider.tf" \
  | sort | xargs cat > <generated_dir>/generated.tf
```

Tell the user: *"Merged Terraformer resource files into generated.tf."*

### 7b. Detect state directory

```bash
find <generated_dir>/aws -name "terraform.tfstate" | wc -l
```

If any exist, pass `--state-dir <generated_dir>/aws` to the engine.

### 7c. Run the engine

```bash
python3 <engine_path> <generated_dir>/generated.tf <output_dir> [--state-dir <generated_dir>/aws]
```

Show the full engine output.

## Step 8 — Format and validate

```bash
terraform fmt <output_dir>
```

Copy the `versions.tf` created in Step 4 into the output dir (it already has the right provider
and region):

```bash
cp <generated_dir>/versions.tf <output_dir>/versions.tf
```

Then run plan to confirm zero drift:

```bash
cd <output_dir>
terraform init
terraform plan   # should show: No changes.
```

Note: `terraform plan` requires valid AWS credentials at plan time as well.

## Step 9 — Report results

Summarise:
- AWS account and region imported from
- Resource types and count imported by Terraformer
- How many resource blocks remained after noise + default removal
- Output files created and what each contains
- Whether `terraform.tfstate` was merged

## Notes

- Never modify the Terraformer-generated files — the engine only reads them
- If the user only has Terraformer output already (no live import needed), the `tf-refactor`
  skill handles that case directly — suggest it instead
- The output directory is safe to re-run into — all files are overwritten
- Always retrieve the live resource list with `terraformer import aws list` — never assume
  resource names from memory, as they vary between Terraformer builds
SKILL_EOF

echo "✓ Skill written:    ${BOB_SKILLS_DIR}/aws-to-iac/SKILL.md"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo "Installation complete. Start a new Bob conversation to use the skills."
echo ""
echo "  Bob skill: tf-refactor  — refactor existing Terraformer output"
echo "  Bob skill: aws-to-iac   — import live AWS infra + refactor to clean IaC"
echo ""
echo "To update later:  git pull  (engine updates are picked up automatically)"
echo "To reinstall:     ./install.sh"
