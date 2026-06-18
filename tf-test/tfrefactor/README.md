# tfrefactor

AI-assisted Terraform refactoring tool.

## Goal 1 — Detect & Reuse Modules

Scans raw Terraformer-generated `.tf` files, finds groups of resources that share
the same attribute-key structure (i.e. identical fingerprint), and emits a proper
reusable Terraform module for each group plus a root `main.tf` that calls it once
per instance.

## Quick start

```bash
cd tfrefactor
pip install -r requirements.txt

# Run the tool against the sample generated files
python -m tfrefactor.cli ../generated.tf --out ../refactored

# Run tests
python -m pytest tests/ -v
```

## Output structure

```
refactored/
├── providers.tf
├── locals.tf
├── variables.tf          (only required inputs)
├── main.tf               (module{} calls only)
├── outputs.tf
└── modules/
    ├── aws_subnet/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── aws_vpc/
    ├── aws_internet_gateway/
    └── aws_instance/
```
