#!/usr/bin/env python3

import base64
import binascii
import csv
import glob
import hashlib
import json
import os
import subprocess
import sys
import yaml


class Error(Exception):
    def __init__(self, message, cause=None, prefix=""):
        if cause:
            super().__init__(f"\n{prefix}{type(cause).__name__} {message}: {cause}")
        else:
            super().__init__(f"\n{prefix}{message}")


def initialize():
    global SCRIPT_DIRECTORY, KUBESEAL_PATH, KUBERNETES_NAMESPACE, KUBERNETES_NAMESPACE, GITHUB_SECRETS_JSON, CERTIFICATE_PATH, GITHUB_SECRETS, SECRETS_MAP_GLOBS
    SCRIPT_DIRECTORY = os.path.dirname(__file__)
    KUBESEAL_PATH = f"{SCRIPT_DIRECTORY}/kubeseal"
    try:
        KUBERNETES_NAMESPACE = os.environ["INPUT_KUBERNETES_NAMESPACE"]
        ENVIRONMENT = os.environ["INPUT_ENVIRONMENT"]
        GITHUB_SECRETS_JSON = os.environ["INPUT_GITHUB_SECRETS_JSON"]
    except KeyError as err:
        raise Error(f"Missing required environment variable: {err}")
    CERTIFICATE_PATH = (
        f"{SCRIPT_DIRECTORY}/certificates/{ENVIRONMENT}_sealedsecrets.crt"
    )
    try:
        GITHUB_SECRETS = json.loads(GITHUB_SECRETS_JSON)
    except json.decoder.JSONDecodeError as err:
        raise Error(
            f"Error decoding INPUT_GITHUB_SECRET_JSON environment variable as JSON: {err}"
        )
    SECRETS_MAP_GLOBS = [
        f"kubernetes/*/overlays/*{ENVIRONMENT}/*seal-github-secrets*.csv",
        f"kubernetes/*/overlays/*{ENVIRONMENT}/.*seal-github-secrets*.csv",
        f"kubernetes/*/overlays/*{ENVIRONMENT}/**/*seal-github-secrets*.csv",
        f"kubernetes/*/overlays/*{ENVIRONMENT}/**/.*seal-github-secrets*.csv",
    ]


def run_kubeseal(sealedsecret_name, secret_data, kubeseal_args):
    secret_manifest_yaml = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": sealedsecret_name},
        "data": secret_data,
    }
    kubeseal_result = subprocess.run(
        [
            KUBESEAL_PATH,
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
        input=yaml.dump(secret_manifest_yaml, encoding="utf-8"),
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
            sealedsecret_name, {}, ["--allow-empty-data"]
        )
        with open(sealedsecret_path, "wb") as sealedsecret_file:
            sealedsecret_file.write(new_sealedsecret_content)
        return None


def update_sealedsecret(
    sealedsecret_path,
    sealedsecret_name,
    sealedsecret_data_key,
    sealedsecret_data_value_base64,
    value_sha256_annotation_key,
    new_value_sha256,
):
    run_kubeseal(
        sealedsecret_name,
        {sealedsecret_data_key: sealedsecret_data_value_base64},
        ["--merge-into", sealedsecret_path],
    )
    sealedsecret_yaml = read_yaml_file(sealedsecret_path)
    ensure_annotations(sealedsecret_yaml)[
        value_sha256_annotation_key
    ] = new_value_sha256
    with open(sealedsecret_path, "w") as sealedsecret_file:
        yaml.dump(sealedsecret_yaml, sealedsecret_file)


def process_secrets_map_row(secrets_map_path, line_number, secrets_map_row):
    try:
        try:
            github_secret_name = secrets_map_row["github_secret_name"]
            sealedsecret_name = secrets_map_row["sealedsecret_name"]
            sealedsecret_data_key = secrets_map_row["sealedsecret_data_key"]
            is_base64_encoded = secrets_map_row.get("is_base64_encoded")
        except KeyError as err:
            raise Error(f"CSV file is missing column: {err}")
        if github_secret_name not in GITHUB_SECRETS:
            raise Error(
                f"Secret named '{github_secret_name}' not found in Github secrets"
            )
        if is_base64_encoded:
            github_secret_value_base64 = GITHUB_SECRETS[github_secret_name]
            try:
                github_secret_value_plain = base64.b64decode(github_secret_value_base64)
            except binascii.Error as err:
                raise Error(
                    f"Github secret '{github_secret_name}' is not valid base64: {err}"
                )
        else:
            github_secret_value_plain = GITHUB_SECRETS[github_secret_name].encode(
                "utf-8"
            )
            github_secret_value_base64 = base64.b64encode(
                github_secret_value_plain
            ).decode("utf-8")
        value_sha256_annotation_key = (
            f"bbyhealth.com/data.{sealedsecret_data_key}.sha256"
        )
        sealedsecret_path = (
            f"{os.path.dirname(secrets_map_path)}/{sealedsecret_name}_sealedsecret.yaml"
        )
        old_value_sha256 = initialize_sealedsecret(
            sealedsecret_path, sealedsecret_name, value_sha256_annotation_key
        )
        new_value_sha256 = hashlib.sha256(github_secret_value_plain).hexdigest()
        if new_value_sha256 != old_value_sha256:
            print(
                f"Updating data value for '{sealedsecret_data_key}' in '{sealedsecret_path}' from '{github_secret_name}'"
            )
            update_sealedsecret(
                sealedsecret_path,
                sealedsecret_name,
                sealedsecret_data_key,
                github_secret_value_base64,
                value_sha256_annotation_key,
                new_value_sha256,
            )
        else:
            print(
                f"Skipping unchanged data value for '{sealedsecret_data_key}' in '{sealedsecret_path}' from '{github_secret_name}'"
            )
    except BaseException as exc:
        raise Error(f"while processing CSV line {line_number}", exc) from exc


def run():
    for secrets_map_glob in SECRETS_MAP_GLOBS:
        secrets_map_paths = glob.iglob(
            secrets_map_glob,
            recursive=False,
        )
        for secrets_map_path in secrets_map_paths:
            try:
                print(f"Processing '{secrets_map_path}'")
                with open(secrets_map_path, mode="r") as secrets_map_file:
                    secrets_map_csv_reader = csv.DictReader(secrets_map_file)
                    line_number = 1
                    for secrets_map_row in secrets_map_csv_reader:
                        line_number += 1
                        process_secrets_map_row(
                            secrets_map_path, line_number, secrets_map_row
                        )
            except BaseException as exc:
                raise Error(
                    f"while processing CSV file '{secrets_map_path}'", exc
                ) from exc


def main():
    initialize()
    run()


try:
    main()
except BaseException as exc:
    raise Error(f"while updating sealed secrets from Github", exc, "\n") from exc
