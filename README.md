# terraform-refactor
AI refactoring tool to convert imported .tf files into proper Terraform IaC. Made for the 2026 IBM Austin Bobathon.

# Use Case & Features
Importing external infrastructure into Terraform can be complicated, especially if the project is highly complex or insufficiently documented. The imported files are often bloated and inefficient, particularly after manual editing. This tool analyzes import files and cleans them up by:
- Detecting existing similar modules that can be reconfigured
- Removing default parameters and requesting further specification where appropriate
- Grouping identical variables
- Separating code into organized sub-files instead of one huge master file
- etc.

# Contributors
- Lucas Lotze
- Christopher Myers
- Brian Thompson
- Austin Wu
- Joe Yang
- Brian Yee
