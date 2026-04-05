# Icarus Mod Validator

Automated validation for Icarus EXMOD/EXMODZ mod files. Catches errors before they reach players.

Built for [JimK72's Mod Manager](https://github.com/JimK72/Icarus-Mod-Manager) format.

## What It Checks

**Schema & Required Fields**
- All required fields present: `name`, `author`, `version`, `description`, `fileName`
- Correct data types for each field
- Valid JSON syntax and UTF-8 encoding

**Version Format**
- Semver (`1.0`, `1.0.0`, `v1.2.3`)
- Week-based (`w132`, `W125`)
- Semver with metadata (`1.0.0-beta`)

**Data Table Structure**
- `CurrentFile` follows `Category-D_TableName.json` naming
- Every `File_Items` entry has a `Name` identifier
- `NSLOCTEXT()` strings are properly formatted
- Icon paths start with `/Game/Assets/`
- Workshop item costs have valid `Amount` values
- Talent grid entries have `Position` and `Size`
- Duplicate table references flagged

**File References & Packaging**
- EXMODZ zip structure: EXMOD must be in `Extracted Mods/` folder
- Detects EXMOD files in wrong locations

**README & Mod Quality**
- README.md presence and minimum content
- Installation instructions mentioned
- Compatibility/week version noted
- Changelog section present
- Placeholder detection (author, description)

## Setup: GitHub Actions (Recommended)

Add the workflow to your mod repo. It runs automatically on push/PR when mod files change.

### Option 1: Copy the workflow file

1. Create `.github/workflows/` in your mod repo
2. Copy `validate-mod.yml` into it
3. Commit and push

### Option 2: One-liner setup

```bash
mkdir -p .github/workflows && \
curl -sL https://raw.githubusercontent.com/AgentKush/icarus-modinfo-validator/main/.github/workflows/validate-mod.yml \
  -o .github/workflows/validate-mod.yml && \
git add .github/workflows/validate-mod.yml && \
git commit -m "Add Icarus mod validation workflow"
```

### What happens

- **On push**: Validates any changed `.EXMOD`, `.EXMODZ`, or `modinfo.json` files
- **On PR**: Validates and posts a comment with results (pass/fail + details)
- **Manual**: Run from Actions tab, optionally specify a subdirectory

### PR Comment Example

> ## ✅ Mod Validation Passed
> ```
> ══════════════════════════════════════════════════════════════
>   Validating: MyMod.EXMOD
> ══════════════════════════════════════════════════════════════
>   ℹ️ INFO: README doesn't include a changelog section.
>
>   ✅ PASSED — 0 error(s), 0 warning(s)
> ```

## Local Usage

You can also run the validator locally:

```bash
# Validate a single EXMOD file
python validate_modinfo.py path/to/MyMod.EXMOD

# Validate an EXMODZ package
python validate_modinfo.py path/to/MyMod.EXMODZ

# Scan a directory for all mod files
python validate_modinfo.py path/to/mods/

# GitHub Actions annotation mode (auto-detected in CI)
python validate_modinfo.py --github path/to/MyMod.EXMOD
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Errors found (mod will likely fail to load) |
| 2 | Warnings only (mod may work but has issues) |

## Requirements

- Python 3.8+ (no external dependencies)

## Example Output

```
══════════════════════════════════════════════════════════════
  Validating: BrokenMod.EXMOD
══════════════════════════════════════════════════════════════
  ❌ ERROR: Missing required field: "author"
  ❌ ERROR [Rows[0]]: Missing "CurrentFile" in row entry
  ⚠️ WARNING: Version "latest" doesn't match expected formats
  ⚠️ WARNING: Description appears to be a placeholder: "a mod"
  ⚠️ WARNING: No README file found.

  ❌ FAILED — 2 error(s), 3 warning(s)
```

## Contributing

PRs welcome! Especially:
- New validation rules for edge cases you've hit
- Additional data table names as Icarus updates
- Improved error messages

## License

MIT — use it however you want.
