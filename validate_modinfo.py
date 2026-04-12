#!/usr/bin/env python3
"""
Icarus EXMOD / modinfo.json Validator
Validates mod files for JimK72's Mod Manager compatibility.

Checks:
  - JSON syntax and encoding
  - Required top-level fields (name, author, version, etc.)
  - Version format (semver or week-based)
  - Row/data table structure and naming conventions
  - File references (CurrentFile table names)
  - README presence and content quality
  - Mod naming conventions
  - EXMODZ packaging structure
  - Blueprint (BP) asset validation (uasset/uexp pairs)
  - PAK file validation (naming convention, location, packaging)

Usage:
  python validate_modinfo.py path/to/ModName.EXMOD
  python validate_modinfo.py path/to/ModName.EXMODZ
  python validate_modinfo.py path/to/directory  (scans for all EXMOD/EXMODZ)

Exit codes:
  0 = all checks passed
  1 = errors found (mod will likely fail to load)
  2 = warnings only (mod may work but has issues)
"""

import json
import os
import re
import sys
import zipfile
from pathlib import Path


# ── Schema ────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "name": str,
    "author": str,
    "version": str,
    "description": str,
    "fileName": str,
}

OPTIONAL_FIELDS = {
    "week": str,
    "Level2": str,
    "Rows": list,
}

# Valid data table file patterns: Category-D_TableName.json
VALID_TABLE_CATEGORIES = {
    "Items", "MetaWorkshop", "Talents", "Processors", "Crafting",
    "Traits", "Modifiers", "Rewards", "Loot", "Stats",
    "Missions", "Weather", "Tech", "Buildable", "Fish",
    "Creature", "Harvestable", "Deployable", "DLC", "Meta",
    "Equipment", "Consumables", "Resources", "Workshop",
    "AI", "Armour", "Building", "Character", "Deployables",
    "Experience", "Farming", "Horde", "Inventory", "Prospects",
    "Scaling", "UI", "World",
}

VALID_TABLE_NAMES = {
    # Core item/equipment tables
    "D_ItemTemplate", "D_Itemable", "D_Equippable", "D_ItemsStatic",
    "D_Inventory", "D_InventoryInfo", "D_Durable", "D_Meshable",
    # Workshop and crafting
    "D_WorkshopItems", "D_ProcessorRecipes", "D_Processing",
    "D_RecipeSets", "D_Consumable", "D_Decayable", "D_Combustible",
    # Talents and meta
    "D_Talents", "D_TalentArchetypes", "D_TalentTrees",
    "D_ModifierStates", "D_MetaCurrency",
    # Building and deployables
    "D_Buildable", "D_BuildingPieces", "D_BuildingSkins",
    "D_Deployable", "D_DeployableSetup", "D_VoxelSetupData",
    # Creatures and AI
    "D_AICreatureType", "D_AIGrowth", "D_AISpawnZones",
    "D_AutonomousSpawns", "D_EpicCreatures", "D_Turret",
    # Farming, fish, world
    "D_Farmable", "D_FarmingGrowthStates", "D_FishSpawnZones",
    "D_Harvestable", "D_OreDeposit", "D_Biomes", "D_MapIcons",
    # Stats, scaling, weather
    "D_StatAfflictions", "D_AfflictionChance", "D_ScalingRules",
    "D_CharacterCreationData", "D_CharacterStartingStats",
    "D_WeatherEvents", "D_WeatherActions", "D_WeatherPools",
    # Experience, rewards, prospects
    "D_ExperienceEvents", "D_ItemRewards",
    "D_ProspectList", "D_ProspectStats", "D_HordeWave",
    # Armour
    "D_ArmourSetBonus", "D_ArmourSets",
}

VERSION_PATTERNS = [
    re.compile(r"^\d+\.\d+(\.\d+)?$"),          # semver: 1.0, 1.0.0
    re.compile(r"^v?\d+\.\d+(\.\d+)?$"),         # v-prefix: v1.0, v1.0.0
    re.compile(r"^[wW]\d+$"),                     # week: w132, W132
    re.compile(r"^\d+\.\d+\.\d+[-+].+$"),        # semver+meta: 1.0.0-beta
]

NSLOCTEXT_PATTERN = re.compile(
    r'^NSLOCTEXT\(\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*\)$'
)

ICON_PATH_PATTERN = re.compile(r"^/Game/Assets/")


# ── Result classes ────────────────────────────────────────────────────────────

class Issue:
    def __init__(self, level, message, location=None):
        self.level = level  # "error", "warning", "info"
        self.message = message
        self.location = location

    def __str__(self):
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.level, "?")
        loc = f" [{self.location}]" if self.location else ""
        return f"  {icon} {self.level.upper()}{loc}: {self.message}"


class ValidationResult:
    def __init__(self, file_path):
        self.file_path = file_path
        self.issues = []

    def error(self, msg, location=None):
        self.issues.append(Issue("error", msg, location))

    def warning(self, msg, location=None):
        self.issues.append(Issue("warning", msg, location))

    def info(self, msg, location=None):
        self.issues.append(Issue("info", msg, location))

    @property
    def errors(self):
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == "warning"]

    @property
    def passed(self):
        return len(self.errors) == 0

    def summary(self):
        errs = len(self.errors)
        warns = len(self.warnings)
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        return f"{status} — {errs} error(s), {warns} warning(s)"


# ── Validators ────────────────────────────────────────────────────────────────

def validate_json_syntax(content, result):
    """Check JSON is valid and parseable."""
    # Strip UTF-8 BOM if present (common in Windows-created files)
    if content.startswith("\ufeff"):
        content = content[1:]
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            result.error("Root element must be a JSON object, not " + type(data).__name__)
            return None
        return data
    except json.JSONDecodeError as e:
        result.error(f"Invalid JSON syntax: {e}")
        return None


def validate_encoding(content_bytes, result):
    """Check file uses UTF-8 encoding."""
    try:
        content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        result.error("File is not valid UTF-8. Mod Manager requires UTF-8 encoding.")
        # Try to decode anyway for further validation
    # Check for BOM
    if content_bytes[:3] == b"\xef\xbb\xbf":
        result.warning("File has UTF-8 BOM marker. This usually works but is unnecessary.")


def validate_required_fields(data, result):
    """Check all required top-level fields exist with correct types."""
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            result.error(f'Missing required field: "{field}"')
        elif not isinstance(data[field], expected_type):
            result.error(
                f'Field "{field}" must be {expected_type.__name__}, '
                f"got {type(data[field]).__name__}"
            )

    for field, expected_type in OPTIONAL_FIELDS.items():
        if field in data and not isinstance(data[field], expected_type):
            result.warning(
                f'Optional field "{field}" should be {expected_type.__name__}, '
                f"got {type(data[field]).__name__}"
            )


def validate_mod_name(data, result):
    """Check mod name conventions."""
    name = data.get("name", "")
    filename = data.get("fileName", "")

    if not name:
        return  # Already caught by required fields check

    if len(name) < 2:
        result.warning("Mod name is very short (less than 2 characters)")

    if len(name) > 100:
        result.warning("Mod name is very long (over 100 characters)")

    # Check name matches fileName (normalize for comparison)
    if filename and name:
        # Normalize: remove special chars, spaces, underscores, lowercase
        norm_name = re.sub(r"[^a-z0-9]", "", name.lower())
        norm_file = re.sub(r"[^a-z0-9]", "", filename.lower())
        if norm_name != norm_file and norm_name not in norm_file and norm_file not in norm_name:
            result.warning(
                f'"name" ({name}) differs from "fileName" ({filename}). '
                "These should usually match for Mod Manager compatibility."
            )

    # Check for invalid characters in fileName
    if filename:
        invalid_chars = re.findall(r'[<>:"/\\|?*]', filename)
        if invalid_chars:
            result.error(
                f'"fileName" contains invalid characters: {invalid_chars}. '
                "This will cause file system errors."
            )

        if " " in filename:
            result.warning(
                '"fileName" contains spaces. Consider using underscores or '
                "camelCase for better cross-platform compatibility."
            )


def validate_author(data, result):
    """Check author field."""
    author = data.get("author", "")
    if not author:
        return

    if len(author) < 2:
        result.warning("Author name is very short")

    if author.lower() in ("author", "your name", "unknown", "anonymous", "test"):
        result.warning(f'Author appears to be a placeholder: "{author}"')


def validate_version(data, result):
    """Check version string format."""
    version = data.get("version", "")
    if not version:
        return  # Already caught by required fields

    if not any(p.match(version) for p in VERSION_PATTERNS):
        result.warning(
            f'Version "{version}" doesn\'t match expected formats: '
            "semver (1.0, 1.0.0), week (w132), or v-prefix (v1.0)"
        )


def validate_week(data, result):
    """Check week compatibility field."""
    week = data.get("week", "")
    if not week:
        return  # Week is optional

    # "All" means compatible with all versions
    if week.lower() == "all":
        return

    if not re.match(r"^[wW]?\d+$", week):
        result.warning(
            f'Week field "{week}" doesn\'t match expected format (e.g., "132", "w132", or "All")'
        )


def validate_description(data, result):
    """Check description quality."""
    desc = data.get("description", "")
    if not desc:
        return

    if len(desc) < 10:
        result.warning("Description is very short. Consider adding more detail for users.")

    if desc.lower() in ("description", "a mod", "my mod", "test", "todo"):
        result.warning(f'Description appears to be a placeholder: "{desc}"')


def validate_rows(data, result):
    """Validate the Rows array structure and content."""
    rows = data.get("Rows", [])
    if not rows:
        result.info("Mod has no Rows — it won't modify any game data tables.")
        return

    if not isinstance(rows, list):
        result.error('"Rows" must be an array')
        return

    seen_tables = set()

    for i, row in enumerate(rows):
        loc = f"Rows[{i}]"

        if not isinstance(row, dict):
            result.error(f"Row entry must be an object, got {type(row).__name__}", loc)
            continue

        # Check CurrentFile
        current_file = row.get("CurrentFile")
        if not current_file:
            result.error('Missing "CurrentFile" in row entry', loc)
            continue

        if not isinstance(current_file, str):
            result.error('"CurrentFile" must be a string', loc)
            continue

        # Validate table file naming: Category-D_TableName.json
        table_match = re.match(r"^(\w+)-(D_\w+)\.json$", current_file)
        if not table_match:
            result.warning(
                f'"{current_file}" doesn\'t match expected format: '
                "Category-D_TableName.json",
                loc,
            )
        else:
            category = table_match.group(1)
            table_name = table_match.group(2)

            if category not in VALID_TABLE_CATEGORIES:
                result.info(
                    f'Table category "{category}" is not in common categories. '
                    "This may be a custom or newer table.",
                    loc,
                )

            if table_name not in VALID_TABLE_NAMES:
                result.info(
                    f'Table "{table_name}" is not in common tables. '
                    "This may be a custom or newer table.",
                    loc,
                )

        # Check for duplicate table references
        if current_file in seen_tables:
            result.warning(
                f'Table "{current_file}" appears multiple times in Rows. '
                "Consider merging File_Items into a single entry.",
                loc,
            )
        seen_tables.add(current_file)

        # Check File_Items
        file_items = row.get("File_Items")
        if file_items is None:
            result.error('Missing "File_Items" in row entry', loc)
            continue

        if not isinstance(file_items, list):
            result.error('"File_Items" must be an array', loc)
            continue

        if len(file_items) == 0:
            result.warning('"File_Items" is empty — this row does nothing', loc)

        # Validate individual items
        for j, item in enumerate(file_items):
            item_loc = f"{loc}.File_Items[{j}]"
            validate_file_item(item, current_file, item_loc, result)


def validate_file_item(item, table_file, loc, result):
    """Validate an individual File_Items entry."""
    if not isinstance(item, dict):
        result.error(f"Item must be an object, got {type(item).__name__}", loc)
        return

    # Every item needs a Name (row identifier)
    name = item.get("Name")
    if not name:
        result.error('Missing "Name" field — every row needs a unique identifier', loc)
    elif not isinstance(name, str):
        result.error('"Name" must be a string', loc)

    # Check NSLOCTEXT format for display strings
    for field in ("DisplayName", "Description"):
        value = item.get(field)
        if value and isinstance(value, str):
            if "NSLOCTEXT" in value and not NSLOCTEXT_PATTERN.match(value):
                result.warning(
                    f'"{field}" has malformed NSLOCTEXT. Expected: '
                    'NSLOCTEXT("Table", "Key", "Display Text")',
                    loc,
                )

    # Check RowName references
    for field in ("Item", "ItemStaticData", "TalentTree", "Archetype", "Model"):
        value = item.get(field)
        if isinstance(value, dict):
            if "RowName" not in value:
                result.warning(
                    f'"{field}" object is missing "RowName" reference',
                    loc,
                )
            elif not isinstance(value["RowName"], str):
                result.error(f'"{field}.RowName" must be a string', loc)
            elif not value["RowName"]:
                result.warning(f'"{field}.RowName" is empty', loc)

    # Check Icon paths
    icon = item.get("Icon")
    if icon and isinstance(icon, str):
        if not ICON_PATH_PATTERN.match(icon):
            result.warning(
                f'Icon path doesn\'t start with /Game/Assets/: "{icon[:60]}..."',
                loc,
            )

    # Check Position/Size for talent grid items
    if "Talents-D_Talents.json" in table_file:
        pos = item.get("Position")
        size = item.get("Size")
        if pos and isinstance(pos, dict):
            if "X" not in pos or "Y" not in pos:
                result.warning("Position should have X and Y coordinates", loc)
        if size and isinstance(size, dict):
            if "X" not in size or "Y" not in size:
                result.warning("Size should have X and Y dimensions", loc)

    # Check cost arrays for workshop items
    if "MetaWorkshop-D_WorkshopItems.json" in table_file:
        for cost_field in ("ResearchCost", "ReplicationCost"):
            costs = item.get(cost_field)
            if costs is not None:
                if not isinstance(costs, list):
                    result.error(f'"{cost_field}" must be an array', loc)
                else:
                    for k, cost in enumerate(costs):
                        if isinstance(cost, dict):
                            if "Amount" not in cost:
                                result.warning(
                                    f'{cost_field}[{k}] missing "Amount"', loc
                                )
                            elif not isinstance(cost["Amount"], (int, float)):
                                result.error(
                                    f'{cost_field}[{k}].Amount must be a number',
                                    loc,
                                )


def validate_readme(mod_dir, result):
    """Check for README presence and quality."""
    readme_candidates = ["README.md", "readme.md", "README.txt", "readme.txt"]
    readme_path = None

    for candidate in readme_candidates:
        path = os.path.join(mod_dir, candidate)
        if os.path.isfile(path):
            readme_path = path
            break

    if not readme_path:
        result.warning(
            "No README file found. A README.md helps users understand your mod."
        )
        return

    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        result.warning(f"Could not read {os.path.basename(readme_path)}")
        return

    if len(content.strip()) < 50:
        result.warning("README is very short (under 50 characters). Consider adding more detail.")

    # Check for common sections
    content_lower = content.lower()
    if "install" not in content_lower:
        result.info("README doesn't mention installation instructions.")
    if "compat" not in content_lower and "week" not in content_lower:
        result.info("README doesn't mention compatibility or game week version.")
    if "changelog" not in content_lower and "change" not in content_lower:
        result.info("README doesn't include a changelog section.")


def validate_exmodz_structure(exmodz_path, result):
    """Validate EXMODZ zip structure matches Mod Manager expectations."""
    if not zipfile.is_zipfile(exmodz_path):
        result.error("File is not a valid ZIP archive")
        return None

    with zipfile.ZipFile(exmodz_path, "r") as zf:
        names = zf.namelist()

        # Check for EXMOD in Extracted Mods/ folder
        exmod_files = [n for n in names if n.startswith("Extracted Mods/") and n.endswith(".EXMOD")]
        if not exmod_files:
            result.error(
                'No EXMOD file found in "Extracted Mods/" folder. '
                "Mod Manager requires the EXMOD at: Extracted Mods/ModName.EXMOD"
            )
            # Check if it's in the wrong location
            all_exmods = [n for n in names if n.endswith(".EXMOD")]
            if all_exmods:
                result.info(
                    f"Found EXMOD at wrong location: {all_exmods[0]}. "
                    "Move it to Extracted Mods/ folder."
                )
            return None
        elif len(exmod_files) > 1:
            result.warning(f"Multiple EXMOD files found: {exmod_files}. Expected one.")

        # Derive mod name from EXMOD filename
        exmod_name = exmod_files[0].replace("Extracted Mods/", "").replace(".EXMOD", "")

        # ── Blueprint (BP) validation ──────────────────────────────────
        bp_files = [n for n in names if "/BP/" in n and not n.endswith("/")]
        if bp_files:
            uasset_files = [n for n in bp_files if n.endswith(".uasset")]
            uexp_files = [n for n in bp_files if n.endswith(".uexp")]

            result.info(f"BP folder found: {len(uasset_files)} .uasset, {len(uexp_files)} .uexp files")

            # Every .uasset should have a matching .uexp (and vice versa)
            uasset_stems = {n.rsplit(".", 1)[0] for n in uasset_files}
            uexp_stems = {n.rsplit(".", 1)[0] for n in uexp_files
                          if not n.endswith(".vanilla.bak")}

            orphan_uassets = uasset_stems - uexp_stems
            orphan_uexps = uexp_stems - uasset_stems

            for stem in orphan_uassets:
                basename = stem.rsplit("/", 1)[-1]
                result.error(
                    f'BP asset "{basename}.uasset" has no matching .uexp file. '
                    "Both files are required for Unreal Engine to load the blueprint."
                )
            for stem in orphan_uexps:
                basename = stem.rsplit("/", 1)[-1]
                result.error(
                    f'BP asset "{basename}.uexp" has no matching .uasset file. '
                    "Both files are required for Unreal Engine to load the blueprint."
                )

            # BP files must be inside the ModName/ folder, not Extracted Mods/
            wrong_location_bp = [n for n in bp_files if n.startswith("Extracted Mods/")]
            if wrong_location_bp:
                result.error(
                    "BP files found inside Extracted Mods/ — they must be in "
                    f'"{exmod_name}/BP/" folder instead.'
                )

        # ── PAK file validation ────────────────────────────────────────
        pak_files = [n for n in names if n.lower().endswith(".pak")]
        if pak_files:
            result.info(f"PAK file(s) found: {', '.join(pak_files)}")

            for pak in pak_files:
                # PAK files should be in ModName/ folder, not Extracted Mods/
                if pak.startswith("Extracted Mods/"):
                    result.error(
                        f'PAK file "{pak}" is inside Extracted Mods/ — '
                        f'move it to "{exmod_name}/" folder.'
                    )

                # PAK naming convention: should end with _P.pak
                pak_basename = pak.rsplit("/", 1)[-1]
                if not pak_basename.endswith("_P.pak"):
                    result.warning(
                        f'PAK file "{pak_basename}" does not follow the _P.pak naming '
                        "convention (e.g. ModName_P.pak). Icarus may not load it."
                    )

                # Warn that PAK mods require server-side install
                result.info(
                    f'PAK mod detected ({pak_basename}). Remember: all players and '
                    "the server must install .pak files to Icarus/Content/Paks/mods/"
                )

        # ── Check for BP on disk but missing from EXMODZ ──────────────
        # (only when we can check the mod directory on disk)
        mod_dir = os.path.dirname(exmodz_path)
        disk_bp_dir = os.path.join(mod_dir, "BP")
        if os.path.isdir(disk_bp_dir) and not bp_files:
            result.error(
                'BP/ folder exists on disk but is NOT included in the EXMODZ package. '
                "Blueprint assets must be packaged inside the EXMODZ for the mod to work."
            )

        # Check for .pak on disk but missing from EXMODZ
        if mod_dir:
            disk_paks = [f for f in os.listdir(mod_dir) if f.lower().endswith(".pak")]
            packaged_pak_names = {p.rsplit("/", 1)[-1] for p in pak_files}
            for dp in disk_paks:
                if dp not in packaged_pak_names:
                    result.warning(
                        f'PAK file "{dp}" exists on disk but is NOT in the EXMODZ package. '
                        "If this PAK is required, it should be included."
                    )

        # Read and return the EXMOD content
        exmod_path = exmod_files[0]
        try:
            content_bytes = zf.read(exmod_path)
            validate_encoding(content_bytes, result)
            return content_bytes.decode("utf-8-sig", errors="replace")
        except Exception as e:
            result.error(f"Failed to read {exmod_path}: {e}")
            return None


# ── Main runner ───────────────────────────────────────────────────────────────

def validate_file(file_path):
    """Run all validations on a single file."""
    result = ValidationResult(file_path)
    file_path = str(file_path)

    if not os.path.exists(file_path):
        result.error(f"File not found: {file_path}")
        return result

    # Handle EXMODZ (zip)
    if file_path.upper().endswith(".EXMODZ"):
        content = validate_exmodz_structure(file_path, result)
        if content is None:
            return result
        mod_dir = os.path.dirname(file_path)
    # Handle EXMOD (plain JSON)
    elif file_path.upper().endswith((".EXMOD", ".JSON")):
        try:
            with open(file_path, "rb") as f:
                content_bytes = f.read()
            validate_encoding(content_bytes, result)
            content = content_bytes.decode("utf-8-sig", errors="replace")
        except Exception as e:
            result.error(f"Failed to read file: {e}")
            return result
        mod_dir = os.path.dirname(file_path)
    else:
        result.error(f"Unsupported file type: {file_path}")
        return result

    # Parse JSON
    data = validate_json_syntax(content, result)
    if data is None:
        return result

    # Run all validators
    validate_required_fields(data, result)
    validate_mod_name(data, result)
    validate_author(data, result)
    validate_version(data, result)
    validate_week(data, result)
    validate_description(data, result)
    validate_rows(data, result)

    # Check for README in the mod's directory
    if mod_dir:
        validate_readme(mod_dir, result)

    return result


def find_mod_files(directory):
    """Recursively find all EXMOD/EXMODZ files in a directory."""
    mod_files = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.upper().endswith((".EXMOD", ".EXMODZ")):
                mod_files.append(os.path.join(root, f))
    return sorted(mod_files)


def print_github_annotations(result):
    """Output GitHub Actions annotations for CI integration."""
    for issue in result.issues:
        if issue.level == "error":
            loc = f" ({issue.location})" if issue.location else ""
            print(f"::error file={result.file_path}::{issue.message}{loc}")
        elif issue.level == "warning":
            loc = f" ({issue.location})" if issue.location else ""
            print(f"::warning file={result.file_path}::{issue.message}{loc}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    github_mode = "--github" in sys.argv or os.environ.get("GITHUB_ACTIONS") == "true"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("Error: No target file or directory specified.")
        print(__doc__)
        sys.exit(1)

    target = args[0]

    # Collect files to validate
    if os.path.isdir(target):
        files = find_mod_files(target)
        if not files:
            print(f"No EXMOD/EXMODZ files found in {target}")
            sys.exit(1)
    else:
        files = [target]

    all_passed = True
    total_errors = 0
    total_warnings = 0

    for filepath in files:
        print(f"\n{'═' * 60}")
        print(f"  Validating: {os.path.basename(filepath)}")
        print(f"{'═' * 60}")

        result = validate_file(filepath)

        # Print issues
        for issue in result.issues:
            print(str(issue))

        # Print summary
        print(f"\n  {result.summary()}")

        # GitHub annotations
        if github_mode:
            print_github_annotations(result)

        if not result.passed:
            all_passed = False
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)

    # Final summary
    if len(files) > 1:
        print(f"\n{'═' * 60}")
        print(f"  TOTAL: {len(files)} file(s), {total_errors} error(s), {total_warnings} warning(s)")
        status = "✅ ALL PASSED" if all_passed else "❌ SOME FAILED"
        print(f"  {status}")
        print(f"{'═' * 60}")

    if total_errors > 0:
        sys.exit(1)
    elif total_warnings > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
