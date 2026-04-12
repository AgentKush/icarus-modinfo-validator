<div align="center">

# Icarus Mod Validator

[![License](https://img.shields.io/github/license/AgentKush/icarus-modinfo-validator?style=flat-square&color=E87B35)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)]()
[![No Dependencies](https://img.shields.io/badge/Dependencies-None-success?style=flat-square)]()

Automated validation for Icarus **EXMOD/EXMODZ** mod files. Catches errors before they reach players.

Built for [JimK72's Mod Manager](https://github.com/Jimk72/Icarus_Software) format.

</div>

---

## What It Checks

**Schema & Fields** — All required fields present (`name`, `author`, `version`, `description`, `fileName`) with correct types. Valid JSON syntax and UTF-8 encoding (BOM stripped automatically).

**Version Format** — Supports semver (`1.0`, `1.0.0`, `v1.2.3`), week-based (`w132`, `W125`), and metadata variants (`1.0.0-beta`).

**Data Table Structure** — `CurrentFile` naming follows `Category-D_TableName.json` convention (including multi-segment categories like `Items-Types-D_BuildingTypes.json`). Every `File_Items` entry has a `Name` identifier. `NSLOCTEXT()` strings validated. Icon paths verified (`/Game/Assets/`). Workshop costs checked for valid `Amount` values. Talent grid entries checked for `Position` and `Size`. Duplicate table references flagged. Recognizes all 78 game categories and 292 data tables sourced directly from Icarus game exports.

**Packaging** — EXMODZ zip structure validated: EXMOD must be inside `Extracted Mods/` folder (Mod Manager requirement).

**Blueprint (BP) Assets** — Validates `.uasset`/`.uexp` pairs inside `ModName/BP/` folders. Detects orphaned assets (missing pair), BP files incorrectly placed inside `Extracted Mods/`, and BP folders on disk that weren't included in the EXMODZ package.

**PAK Files** — Validates `.pak` files follow the `_P.pak` naming convention required by Icarus. Checks PAK files aren't inside `Extracted Mods/`. Detects PAK files on disk missing from the EXMODZ package. Reminds that PAK mods require all players and the server to install.

**Documentation** — README.md presence and content quality. Checks for installation instructions, compatibility notes, and changelog sections. Placeholder detection for author and description fields.

**Catalog (modinfo.json)** — Validates the master mod catalog: required fields per mod, duplicate detection, download URL format, and cross-referencing against actual mod folders.

---

## Quick Start: GitHub Actions

Add automated validation to your Icarus mod repo in one command:

```bash
mkdir -p .github/workflows && \
curl -sL https://raw.githubusercontent.com/AgentKush/icarus-modinfo-validator/main/.github/workflows/validate-mod.yml \
  -o .github/workflows/validate-mod.yml && \
git add .github/workflows/validate-mod.yml && \
git commit -m "Add Icarus mod validation workflow"
```

Or manually copy `.github/workflows/validate-mod.yml` into your repo.

### What Happens

- **On push** — Validates any changed `.EXMOD`, `.EXMODZ`, or `modinfo.json` files
- **On PR** — Validates and posts a comment with pass/fail results
- **Manual** — Run from the Actions tab with an optional subdirectory path

### PR Comment Example

> ## Mod Validation Passed
> ```
> ══════════════════════════════════════════════════════════════
>   Validating: MyMod.EXMOD
> ══════════════════════════════════════════════════════════════
>   ℹ️ INFO: README doesn't include a changelog section.
>
>   ✅ PASSED — 0 error(s), 0 warning(s)
> ```

---

## Local Usage

Run the validator directly from the command line:

```bash
# Validate a single EXMOD file
python validate_modinfo.py MyMod/MyMod.EXMOD

# Validate an EXMODZ package (checks zip structure too)
python validate_modinfo.py MyMod/MyMod.EXMODZ

# Scan an entire directory for all mod files
python validate_modinfo.py ./mods/

# GitHub Actions annotation mode (auto-detected in CI)
python validate_modinfo.py --github MyMod/MyMod.EXMOD
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed |
| `1` | Errors found — mod will likely fail to load |
| `2` | Warnings only — mod may work but has issues |

### Example Output

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

---

## Validation Rules Reference

### Required EXMOD Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name of the mod |
| `author` | string | Mod author (not a placeholder) |
| `version` | string | Version in supported format |
| `description` | string | What the mod does (min 10 chars) |
| `fileName` | string | Base filename without extension |

### Supported Data Tables

The validator recognizes all 78 table categories and 292 table names from the Icarus game exports, covering every moddable data table in the game — from core items (`D_ItemTemplate`, `D_ItemsStatic`) to crafting (`D_ProcessorRecipes`, `D_RecipeSets`), talents (`D_Talents`, `D_TalentTrees`), AI (`D_AICreatureType`, `D_GOAPSetup`), weather (`D_WeatherEvents`, `D_Biomes`), combat (`D_FirearmData`, `D_CriticalHitSetup`), vehicles (`D_VehicleSetups`, `D_Mounts`), and more.

### EXMODZ Structure

```
ModName.EXMODZ (zip)
├── Extracted Mods/
│   └── ModName.EXMOD          ← Required location
└── ModName/
    ├── Readme (ModName_P.pak).txt
    ├── README.md
    ├── Banner.png
    ├── BP/                    ← Blueprint assets (optional)
    │   ├── Asset.uasset       ← Must have matching .uexp
    │   └── Asset.uexp
    └── ModName_P.pak          ← PAK file (optional)
```

### Blueprint & PAK Rules

| Rule | Severity |
|------|----------|
| Every `.uasset` must have a matching `.uexp` (and vice versa) | Error |
| BP files must be in `ModName/BP/`, never in `Extracted Mods/` | Error |
| BP folder on disk but missing from EXMODZ | Error |
| PAK files must follow `_P.pak` naming convention | Warning |
| PAK files must not be in `Extracted Mods/` | Error |
| PAK file on disk but missing from EXMODZ | Warning |

---

## Requirements

Python 3.8+ with no external dependencies. Uses only standard library modules: `json`, `os`, `re`, `sys`, `zipfile`, `pathlib`.

## Contributing

PRs welcome, especially for new validation rules, additional data table names as Icarus updates, and improved error messages.

## License

[MIT](LICENSE) — use it however you want.

---

<div align="center">

**Part of [AgentKush's Icarus Mods](https://github.com/AgentKush/Icarus-mods)** — 38 mods, 37,500+ data entries, 18,800+ recipes

</div>
