import csv
import json
import os
import re

def inspect_csv(file_path):
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"
    
    with open(file_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return "Empty CSV"
        
        rows = list(reader)
        row_count = len(rows)
        col_count = len(header)
        
        try:
            sku_idx = header.index('sku_number')
            skus = [row[sku_idx] for row in rows]
            unique_skus = len(set(skus))
            
            row_tuples = [tuple(r) for r in rows]
            duplicate_rows = len(row_tuples) - len(set(row_tuples))
            
            sku_counts = {}
            for s in skus:
                sku_counts[s] = sku_counts.get(s, 0) + 1
            duplicate_sku_rows = sum(count - 1 for count in sku_counts.values() if count > 1)
        except ValueError:
            unique_skus = "N/A"
            duplicate_rows = "N/A"
            duplicate_sku_rows = "N/A"

        deny_patterns = [
            r'^store_number$', r'^promotion_header_key$', r'^promotion_row_key$', 
            r'^store_number_key$', r'^sku_number_key$', r'^promotional_sku_id_key$',
            r'.*_key$', r'^raw_.*', r'^internal_.*', r'^registry_.*', 
            r'^extraction_.*', r'^audit_.*', r'^debug_.*', r'^diagnostic_.*', r'^feature_.*'
        ]
        internal_cols = [col for col in header if any(re.match(p, col) for p in deny_patterns)]

    return {
        "row_count": row_count,
        "col_count": col_count,
        "unique_skus": unique_skus,
        "duplicate_rows": duplicate_rows,
        "duplicate_sku_rows": duplicate_sku_rows,
        "internal_cols": internal_cols
    }

def read_json(file_path):
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r') as f:
        try:
            return json.load(f)
        except:
            return None

# Paths
base = "/Users/paulmorison/promotions_runtime_governed_stage12_3000_proof_20260518_rerun"
allocation_csv = f"{base}/promotions/priceline/772/prediction/2026-05-21/772_2026-05-21_allocation-report-wk47-48-winter-part-1.csv"
split_json = f"{base}/inspection/promotions-stage12-3000-live-20260518T000015Z/commercial_publishability_split.json"

print("--- 1, 2, 3: Allocation CSV Inspection ---")
alloc_info = inspect_csv(allocation_csv)
if isinstance(alloc_info, dict):
    print(f"Row count (excl header): {alloc_info['row_count']}")
    print(f"Column count: {alloc_info['col_count']}")
    print(f"Unique sku_number count: {alloc_info['unique_skus']}")
    print(f"Duplicate full-row count: {alloc_info['duplicate_rows']}")
    print(f"Duplicate sku_number row count: {alloc_info['duplicate_sku_rows']}")
    print(f"Internal/technical columns: {alloc_info['internal_cols']}")
else:
    print(alloc_info)

print("\n--- 4: Reconciliation ---")
split_data = read_json(split_json)
if split_data:
    source_rows = split_data.get('total_decision_surface_rows', 0)
    registry_dupes = split_data.get('registry_duplicate_rows', 0)
    # Post-registry is often defined as total minus duplicates
    post_registry = source_rows - registry_dupes
    # Final publishable is explicitly named
    publishable = split_data.get('final_publishable_rows', 0)
    # Residual policy-excluded or review-required
    policy_excluded = split_data.get('review_required_rows', 0) + split_data.get('policy_excluded_legitimate_rows', 0)
    
    print(f"Source/Total rows: {source_rows}")
    print(f"Registry duplicate rows: {registry_dupes}")
    print(f"Post-registry/Post-policy review rows: {post_registry}")
    print(f"Final publishable rows: {publishable}")
    print(f"Residual policy-excluded rows: {policy_excluded}")
    
    checksum = publishable + policy_excluded + registry_dupes
    print(f"Row-conserving sum (Pub + Excl + RegistryDupes): {checksum}")
    if checksum == source_rows:
        print("Reconciliation: PASS")
    else:
        print(f"Reconciliation: FAIL (Diff: {source_rows - checksum})")
else:
    print(f"Split JSON not found or unreadable at {split_json}")

