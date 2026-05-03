import argparse
import csv
import json
import os
import shutil
import sys

import numpy as np

import utils
from cbh.model import CBHModel


TARGET_COLUMN = "target_cbh"
SKIPPED_COLUMNS = {"row", "col", TARGET_COLUMN}


def discover_feature_csvs(paths):
    csv_paths = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for filename in files:
                    if filename == "cbh_features.csv":
                        csv_paths.append(os.path.join(root, filename))
        elif os.path.isfile(path):
            csv_paths.append(path)
        else:
            raise FileNotFoundError(f"Training input not found: {path}")

    unique_paths = []
    seen = set()
    for path in csv_paths:
        normalized = os.path.abspath(path)
        if normalized not in seen:
            unique_paths.append(path)
            seen.add(normalized)
    return unique_paths


def append_to_master_csv(master_path, source_csv_paths):
    if not source_csv_paths:
        raise ValueError("at least one source CSV is required")

    os.makedirs(os.path.dirname(os.path.abspath(master_path)), exist_ok=True)
    master_exists = os.path.exists(master_path) and os.path.getsize(master_path) > 0
    expected_header = None
    appended_rows = 0

    if master_exists:
        with open(master_path, newline="") as master_file:
            reader = csv.reader(master_file)
            expected_header = next(reader, None)
        if not expected_header:
            master_exists = False

    with open(master_path, "a", newline="") as master_file:
        writer = csv.writer(master_file)

        for csv_path in source_csv_paths:
            with open(csv_path, newline="") as source_file:
                reader = csv.reader(source_file)
                header = next(reader, None)
                if not header:
                    continue

                if expected_header is None:
                    expected_header = header
                    if not master_exists:
                        writer.writerow(header)
                        master_exists = True
                elif header != expected_header:
                    raise ValueError(
                        f"CSV header mismatch for {csv_path}. "
                        "All proxy feature CSV files must use the same feature columns."
                    )

                for row in reader:
                    if row:
                        writer.writerow(row)
                        appended_rows += 1

    return {"path": master_path, "appended_rows": appended_rows}


def load_proxy_training_table(csv_paths, nodata=utils.DEFAULT_NODATA):
    csv_paths = discover_feature_csvs(csv_paths)
    if not csv_paths:
        raise ValueError("no cbh_features.csv files were found")

    feature_names = None
    feature_rows = []
    target_values = []

    for csv_path in csv_paths:
        with open(csv_path, newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                continue
            if TARGET_COLUMN not in reader.fieldnames:
                raise ValueError(f"{csv_path} does not include a {TARGET_COLUMN} column")

            current_features = [
                name for name in reader.fieldnames if name not in SKIPPED_COLUMNS
            ]
            if feature_names is None:
                feature_names = current_features
            elif current_features != feature_names:
                raise ValueError(
                    f"Feature column mismatch for {csv_path}. "
                    "All training CSV files must use the same feature columns."
                )

            for row in reader:
                try:
                    target = float(row[TARGET_COLUMN])
                    features = [float(row[name]) for name in feature_names]
                except (TypeError, ValueError):
                    continue

                if (
                    not np.isfinite(target)
                    or target == nodata
                    or any((not np.isfinite(value) or value == nodata) for value in features)
                ):
                    continue

                feature_rows.append(features)
                target_values.append(target)

    if not feature_rows:
        raise ValueError("no valid proxy-labeled feature rows were found")

    return {
        "X": np.asarray(feature_rows, dtype=np.float32),
        "y": np.asarray(target_values, dtype=np.float32),
        "feature_names": feature_names or [],
        "source_files": csv_paths,
    }


def train_proxy_model(
    csv_paths,
    model_path,
    master_csv_path=None,
    append_to_master=False,
    random_state=42,
    forest_kwargs=None,
):
    source_paths = discover_feature_csvs(csv_paths)
    if append_to_master:
        if master_csv_path is None:
            raise ValueError("master_csv_path is required when append_to_master is enabled")
        append_to_master_csv(master_csv_path, source_paths)
        training_paths = [master_csv_path]
    elif master_csv_path is not None and os.path.exists(master_csv_path):
        training_paths = [master_csv_path]
    else:
        training_paths = source_paths

    table = load_proxy_training_table(training_paths)
    model = CBHModel(random_state=random_state, **(forest_kwargs or {}))
    model.feature_names = table["feature_names"]
    model.train(table["X"], table["y"])

    os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
    model.save(model_path)

    latest_path = os.path.join(os.path.dirname(os.path.abspath(model_path)), "cbh_proxy_model_latest.pkl")
    if os.path.abspath(latest_path) != os.path.abspath(model_path):
        shutil.copy2(model_path, latest_path)

    return {
        "model_path": model_path,
        "latest_model_path": latest_path,
        "master_csv_path": master_csv_path,
        "training_rows": int(table["X"].shape[0]),
        "feature_count": int(table["X"].shape[1]),
        "source_files": table["source_files"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train a persistent CBH model from proxy-labeled cbh_features.csv files."
    )
    parser.add_argument("model_path")
    parser.add_argument("inputs", nargs="+", help="cbh_features.csv files or folders to scan")
    parser.add_argument("--master-csv", dest="master_csv_path")
    parser.add_argument("--append-to-master", action="store_true")
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--min-samples-leaf", type=int, default=2)

    args = parser.parse_args()

    try:
        result = train_proxy_model(
            args.inputs,
            args.model_path,
            master_csv_path=args.master_csv_path,
            append_to_master=args.append_to_master,
            random_state=args.random_state,
            forest_kwargs={
                "n_estimators": args.n_estimators,
                "min_samples_leaf": args.min_samples_leaf,
            },
        )
        print(json.dumps({"status": "success", **result}))
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
