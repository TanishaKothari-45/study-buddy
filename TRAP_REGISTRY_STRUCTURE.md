# Trap Registry Structure & Loading

**Date**: 2026-04-04  
**Status**: ✅ Updated for hierarchical domain-specific structure  

---

## New Directory Structure

```
backend/app/prelims_v2/
└─ traps/
   ├─ geography/
   │   ├─ climatology/
   │   │   └─ traps_geography_climatology.json
   │   ├─ oceanography/
   │   │   └─ traps_geography_oceanography.json
   │   └─ geomorphology/
   │       └─ traps_geography_geomorphology.json
   ├─ polity/
   │   ├─ constitution/
   │   │   └─ traps_polity_constitution.json
   │   └─ ...
   └─ [other subjects]/
       └─ [domain]/
           └─ traps_subject_domain.json
```

---

## Loading Fallback Chain

When loading traps for a skeleton, the code tries paths in this order:

1. **Domain-specific** (primary):
   ```
   traps/{subject}/{domain}/traps_{subject}_{domain}.json
   
   Example for Geography/Climatology:
   traps/geography/climatology/traps_geography_climatology.json
   ```

2. **Subject-level** (fallback 1):
   ```
   traps_{subject}.json
   
   Example:
   traps_geography.json
   ```

3. **Config directory** (fallback 2):
   ```
   ../../../config/trap_registry.json
   ```

---

## Implementation

### Pipeline.py (Stage 3)

```python
# Extract domain from topics
domain = topics[1] if len(topics) > 1 else (topics[0] if topics else subject)
domain_lower = domain.lower().replace(" ", "_")
subject_lower = subject.lower().replace(" ", "_")

# Build path: traps/geography/climatology/traps_geography_climatology.json
trap_registry_path = _V2_DIR / "traps" / subject_lower / domain_lower / f"traps_{subject_lower}_{domain_lower}.json"

if not trap_registry_path.exists():
    # Fallback 1: subject-level
    trap_registry_path = _V2_DIR / f"traps_{subject_lower}.json"

if not trap_registry_path.exists():
    # Fallback 2: config directory
    trap_registry_path = _CONFIG_DIR / "trap_registry.json"
```

### Stage5_gap_fill.py (Gap Fill Retries)

```python
# Use skeleton's sub_domain (which is the domain from Stage 0)
domain = getattr(skeleton, "sub_domain", None) or subject

# Build same hierarchical path
trap_registry_path = _v2_dir / "traps" / subject_lower / domain_lower / f"traps_{subject_lower}_{domain_lower}.json"

# Same fallback chain...
```

---

## Trap Registry File Format

Each domain-specific JSON file can use either structure:

### Structure A: Top-level "traps" key
```json
{
  "traps": [
    {
      "trap_id": "GEO_CLIM_T01",
      "trap_name": "El Nino vs Monsoon confusion",
      "description": "...",
      "how_to_generate": "..."
    }
  ]
}
```

### Structure B: "trap_patterns_global_reference" key
```json
{
  "subject": "Geography",
  "domain": "Climatology",
  "description": "...",
  "trap_patterns_global_reference": {
    "GEO_CLIM_T01": {
      "trap_name": "El Nino vs Monsoon confusion",
      "description": "...",
      "how_to_generate": "..."
    },
    "GEO_CLIM_T02": {
      "trap_name": "...",
      ...
    }
  }
}
```

The loading logic (`stage3_generation.py:_get_trap()`) handles both structures automatically.

---

## Expected Logging

When running a test for Geography/Climatology:

```
[V2][STAGE 3] Trap registry path: .../traps/geography/climatology/traps_geography_climatology.json (exists: True)
[Stage3][TrapRegistry] Attempting to load from: .../traps_geography_climatology.json
[Stage3][TrapRegistry] Raw JSON keys: ['subject', 'domain', 'trap_patterns_global_reference', ...]
[Stage3][TrapRegistry] ✅ Loaded 15 traps from 'trap_patterns_global_reference'
[Stage3][Q1/sk_001] GEO_CLIM_T01 trap loaded successfully
```

---

## Migration Guide

If you have existing flat trap files:

**Before:**
```
backend/app/prelims_v2/
├─ traps_geography.json
├─ traps_polity.json
└─ ...
```

**After:**
```
backend/app/prelims_v2/traps/
├─ geography/
│   ├─ climatology/
│   │   └─ traps_geography_climatology.json  (content from old file, domain-filtered)
│   ├─ oceanography/
│   │   └─ traps_geography_oceanography.json
│   └─ ... (other domains)
└─ polity/
    └─ ...
```

To migrate:
1. Create directory structure
2. Split trap data by domain
3. Rename files to `traps_{subject}_{domain}.json`
4. Keep old files as fallback until migration complete

---

## Summary

✅ **Hierarchical structure**: traps/subject/domain/traps_subject_domain.json  
✅ **Domain-specific loading**: Climatology traps only when needed  
✅ **Fallback chain**: Domain → Subject → Config  
✅ **Flexible format**: Handles both "traps" and "trap_patterns_global_reference" keys  
✅ **Syntax passing**: All files compiled successfully  

**Pipeline ready for domain-specific trap loading.** 🚀
