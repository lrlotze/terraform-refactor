---
name: tf-refactor
description: Use when the user wants to refactor, clean up, or convert a Terraform file — including phrases like "refactor my generated.tf", "clean up this terraform", "convert terraformer output", or "make my tf file production ready".
---

# Terraform Refactor Skill

This skill runs the terraform-refactor engine against a Terraformer-generated `.tf` file and produces clean, modular, production-ready Terraform output.

## Step 1 — Find or build the input file

Check the environment in this order:

**A. Active file** — if the user has a `.tf` file open, ask if that's the one to refactor.

**B. Existing `generated.tf`** — search for one with `glob` pattern `**/generated.tf`. If found, use it.

**C. Terraformer split output** — if neither A nor B applies, look for a Terraformer-style directory tree: a folder containing multiple subdirectories each with their own `.tf` files (the classic `generated/aws/vpc/vpc.tf`, `generated/aws/subnet/subnet.tf` layout). Detect this with:
```
glob pattern: "**/aws/**/*.tf"
```

If a split Terraformer tree is found and no combined `generated.tf` exists, **build it automatically**:

```bash
find <generated_aws_dir> -name "*.tf" -not -name "variables.tf" -not -name "outputs.tf" -not -name "provider.tf" | sort | xargs cat > generated.tf
```

Exclude `variables.tf`, `outputs.tf`, and `provider.tf` from the merge — they contain boilerplate that the engine's noise-removal pass already handles, and including duplicates causes parse noise. Only merge the primary resource files (`vpc.tf`, `subnet.tf`, `instance.tf`, etc.).

Tell the user: *"No generated.tf found — built one by merging the Terraformer output files."*

**D. Ask** — if none of the above, use `ask_followup_question` to ask the user which file or folder to use.

Do NOT proceed without a confirmed input file path.

## Step 2 — Confirm the state directory (optional but recommended)

The `--state-dir` flag merges the Terraformer per-module state files so `terraform plan` works immediately after the refactor. Look for it automatically:

- Check for a `generated/aws/` directory alongside the input file
- Check for any directory containing multiple `terraform.tfstate` files

If found, use it automatically and tell the user. If not found, proceed without it and note they can run `terraform import` manually later.

## Step 3 — Determine the output directory

Default: create an `output/` directory next to the input file.
If the user specified a different location, use that.

## Step 4 — Run the pipeline

Use `execute_command` to run the engine:

```bash
python3 engine/main.py <input_file> <output_dir> [--state-dir <state_dir>]
```

If the engine is not at `engine/main.py`, search for it:
```bash
find . -name "main.py" -path "*/engine/*"
```

Show the full output to the user so they can see exactly what was removed and grouped.

## Step 5 — Run terraform fmt on the output

```bash
terraform fmt <output_dir>
```

If `terraform` is not installed, skip this step and note it.

## Step 6 — Report results

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

## Step 7 — Run the test suite (if available)

If `tests/test_pipeline.py` exists in the workspace, offer to run it:

```bash
python3 tests/test_pipeline.py
```

Report pass/fail count.

## Notes

- Never edit the input file — the engine only reads it
- If the engine errors, read the error, diagnose the cause (likely a parsing edge case), and report it clearly
- The output directory is safe to re-run into — files are overwritten each time
