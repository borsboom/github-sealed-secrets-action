#!/usr/bin/env python3

import csv
import glob
import hashlib
import json
import os
import subprocess
import sys
import yaml

KUBERNETES_NAMESPACE = os.environ["INPUT_KUBERNETES_NAMESPACE"]
ENVIRONMENT = os.environ["INPUT_ENVIRONMENT"]
GITHUB_SECRETS_JSON = os.environ["INPUT_GITHUB_SECRETS_JSON"]
CERTIFICATE_PATH = f"/app/certificates/{ENVIRONMENT}_sealedsecrets.crt"
GITHUB_SECRETS = json.loads(GITHUB_SECRETS_JSON)
SECRETS_MAP_GLOBS = [
    f"kubernetes/*/overlays/*{ENVIRONMENT}/*seal-github-secrets*.csv",
    f"kubernetes/*/overlays/*{ENVIRONMENT}/.*seal-github-secrets*.csv",
    f"kubernetes/*/overlays/*{ENVIRONMENT}/**/*seal-github-secrets*.csv",
    f"kubernetes/*/overlays/*{ENVIRONMENT}/**/.*seal-github-secrets*.csv",
]


def run_kubeseal(sealedsecret_name, kubectl_args, kubeseal_args):
    kubectl_result = subprocess.run(
        [
            "/app/kubectl",
            "create",
            "secret",
            "generic",
            sealedsecret_name,
            "--dry-run=client",
            "-o",
            "yaml",
        ]
        + kubectl_args,
        check=True,
        capture_output=True,
    )
    kubeseal_result = subprocess.run(
        [
            "/app/kubeseal",
            "--namespace",
            KUBERNETES_NAMESPACE,
            "--scope",
            "namespace-wide",
            "--cert",
            CERTIFICATE_PATH,
            "-o",
            "yaml",
        ]
        + kubeseal_args,
        check=True,
        capture_output=True,
        input=kubectl_result.stdout,
    )
    return kubeseal_result.stdout


def read_yaml_file(path):
    with open(path, "r") as file:
        return yaml.safe_load(file)


def ensure_annotations(yaml):
    metadata = yaml.get("metadata")
    if metadata is None:
        metadata = {}
        yaml["metadata"] = metadata
    annotations = metadata.get("annotations")
    if annotations is None:
        annotations = {}
        yaml["annotations"] = annotations
    return annotations


def initialize_sealedsecret(
    sealedsecret_path, sealedsecret_name, value_sha256_annotation_key
):
    if os.path.exists(sealedsecret_path):
        sealedsecret_yaml = read_yaml_file(sealedsecret_path)
        return ensure_annotations(sealedsecret_yaml).get(value_sha256_annotation_key)
    else:
        new_sealedsecret_content = run_kubeseal(
            sealedsecret_name, [], ["--allow-empty-data"]
        )
        with open(sealedsecret_path, "wb") as sealedsecret_file:
            sealedsecret_file.write(new_sealedsecret_content)
        return None


def update_sealedsecret(
    sealedsecret_path,
    sealedsecret_name,
    sealedsecret_data_key,
    sealedsecret_data_value,
    value_sha256_annotation_key,
    new_value_sha256,
):
    run_kubeseal(
        sealedsecret_name,
        [
            "--from-literal",
            f"{sealedsecret_data_key}={sealedsecret_data_value}",
        ],
        ["--merge-into", sealedsecret_path],
    )
    sealedsecret_yaml = read_yaml_file(sealedsecret_path)
    ensure_annotations(sealedsecret_yaml)[
        value_sha256_annotation_key
    ] = new_value_sha256
    with open(sealedsecret_path, "w") as sealedsecret_file:
        yaml.dump(sealedsecret_yaml, sealedsecret_file)


def process_secrets_map_row(
    overlay_dir_path, github_secret_name, sealedsecret_name, sealedsecret_data_key
):
    if github_secret_name not in GITHUB_SECRETS:
        sys.exit(f"'{github_secret_name}' not found in Github secrets")
    github_secret_value = GITHUB_SECRETS[github_secret_name]
    value_sha256_annotation_key = f"bbyhealth.com/data/{sealedsecret_data_key}/sha256"
    sealedsecret_path = f"{overlay_dir_path}/{sealedsecret_name}_sealedsecret.yaml"
    old_value_sha256 = initialize_sealedsecret(
        sealedsecret_path, sealedsecret_name, value_sha256_annotation_key
    )
    new_value_sha256 = hashlib.sha256(github_secret_value.encode("utf-8")).hexdigest()
    if new_value_sha256 != old_value_sha256:
        print(
            f"Updating data value for '{sealedsecret_data_key}' in '{sealedsecret_path}'"
        )
        update_sealedsecret(
            sealedsecret_path,
            sealedsecret_name,
            sealedsecret_data_key,
            github_secret_value,
            value_sha256_annotation_key,
            new_value_sha256,
        )


def main():
    for secrets_map_glob in SECRETS_MAP_GLOBS:
        secrets_map_paths = glob.iglob(
            secrets_map_glob,
            recursive=False,
        )
        for secrets_map_path in secrets_map_paths:
            print(f"Processing '{secrets_map_path}'")
            with open(secrets_map_path, mode="r") as secrets_map_file:
                secrets_map_csv_reader = csv.DictReader(secrets_map_file)
                for secrets_map_row in secrets_map_csv_reader:
                    process_secrets_map_row(
                        os.path.dirname(secrets_map_path),
                        secrets_map_row["github_secret_name"],
                        secrets_map_row["sealedsecret_name"],
                        secrets_map_row["sealedsecret_data_key"],
                    )


main()
