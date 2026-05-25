import os
import json
import pandas as pd
import glob

runs = {
    "before": "./tmp/promotions_operator_trust_live_20260518T000005Z/local_inspection/promotions-operator-trust-live-20260518T000005Z",
    "after": "./tmp/promotions_operator_trust_live_20260518T000006Z/local_inspection/promotions-operator-trust-live-20260518T000006Z"
}

def get_path(run_dir, pattern):
    matches = glob.glob(os.path.join(run_dir, "**", pattern), recursive=True)
    return matches[0] if matches else None

results = {}

for key, run_dir in runs.items():
    res = {"path": run_dir}
    
    # Manifest - check parent dir too as it's often "governed"
    manifest_path = get_path(run_dir, "operational_cycle_manifest.json")
    if not manifest_path:
        manifest_path = get_path(os.path.join(run_dir, ".."), "operational_cycle_manifest.json")
    
    if manifest_path:
        res["manifest"] = manifest_path
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            # Stage 6 telemetry
            stage6 = manifest.get("stages", {}).get("6", {})
            res["stage6_telemetry"] = {
                "row_count": list(stage6.get("outputs", {}).values())[0].get("row_count") if stage6.get("outputs") else None,
                "retry_settings": stage6.get("retry_settings")
            }
    
    # Summaries
    res["run_summary"] = get_path(run_dir, "operator_run_summary.json")
    res["cycle_run_summary"] = get_path(run_dir, "operational_cycle_run_summary.json")
    
    # Stage 11 Store 772 CSV
    store_csv = get_path(run_dir, "*772*.csv")
    if store_csv:
        res["store_772_csv"] = store_csv
        df = pd.read_csv(store_csv)
        res["store_772_stats"] = {
            "shape": df.shape,
            "columns": list(df.columns),
            "key_counts": len(df.iloc[:, 0].unique()) if not df.empty else 0
        }

    # Stage 12 Publication Summary
    pub_sum = get_path(run_dir, "publication_summary.csv")
    if not pub_sum:
        pub_sum = get_path(os.path.join(run_dir, ".."), "publication_summary.csv")
    
    if pub_sum:
        res["publication_summary_path"] = pub_sum
        df_pub = pd.read_csv(pub_sum)
        res["publication_summary_rows"] = df_pub.to_dict(orient='records')

    # Split and Gates
    for art in ["commercial_publishability_split.json", "publish_gate_counts.json", "publish_noop_summary.json"]:
        p = get_path(run_dir, art)
        if not p: p = get_path(os.path.join(run_dir, ".."), art)
        if p:
            with open(p, 'r') as f:
                data = json.load(f)
                if "split" in art:
                    res["split_key_counts"] = {k: len(v) if isinstance(v, list) else v for k, v in data.items()}
                elif "gate" in art:
                    res["gate_counts"] = data
                else:
                    res["noop_summary"] = data

    results[key] = res

print(json.dumps(results, indent=2))
