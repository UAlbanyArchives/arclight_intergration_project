import os
import re
import yaml
import shutil
import difflib
from pypdf import PdfReader

def load_config(config_path="./.iiiflow.yml"):
    """Load configuration from the specified YAML file."""
    with open(config_path, "r") as config_file:
        config = yaml.safe_load(config_file)
    return config["discovery_storage_root"], config["error_log_file"]

def iterate_collections_and_objects(discovery_storage_root, action):
    """
    Iterate through all collections and objects in the discovery storage root
    and apply the given action.

    :param discovery_storage_root: Path to the root directory for collections.
    :param action: A function that takes `collection_id`, `object_id`, and `object_path`.
    """
    for collection_id in os.listdir(discovery_storage_root):
        collection_path = os.path.join(discovery_storage_root, collection_id)
        if os.path.isdir(collection_path):
            for object_id in os.listdir(collection_path):
                object_path = os.path.join(collection_path, object_id)
                if os.path.isdir(object_path):
                    action(collection_id, object_id, object_path)


def create_temp_fixture_config(tmp_path, config_path="./.iiiflow.yml"):
    """Copy the configured fixture tree to a temp directory and write a matching temp config."""
    with open(config_path, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    discovery_storage_root = config["discovery_storage_root"]
    temp_discovery_storage_root = tmp_path / "fixtures"
    shutil.copytree(discovery_storage_root, temp_discovery_storage_root)

    config["discovery_storage_root"] = str(temp_discovery_storage_root)
    config["error_log_file"] = os.path.join(str(temp_discovery_storage_root), "errors.log")

    audio_thumbnail_file = config.get("audio_thumbnail_file")
    if audio_thumbnail_file:
        config["audio_thumbnail_file"] = os.path.join(str(temp_discovery_storage_root), os.path.basename(audio_thumbnail_file))

    temp_config_path = tmp_path / ".iiiflow.yml"
    with open(temp_config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file, sort_keys=False)

    return str(temp_discovery_storage_root), str(temp_config_path)


def assert_text_file_matches(actual_path, expected_path):
    """Compare text files while normalizing line endings across host/container boundaries."""
    with open(actual_path, "r", encoding="utf-8") as actual_file, open(expected_path, "r", encoding="utf-8") as expected_file:
        actual_text = actual_file.read().replace("\r\n", "\n")
        expected_text = expected_file.read().replace("\r\n", "\n")

    assert actual_text == expected_text, f"File {actual_path} does not match canonical version."


def normalize_text_for_similarity(text):
    text = text.replace("\r\n", "\n").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def assert_text_file_similar(actual_path, expected_path, min_length_ratio=0.8, min_similarity_ratio=0.9):
    """Compare text files using coarse stability metrics suitable for OCR/transcription output."""
    with open(actual_path, "r", encoding="utf-8") as actual_file, open(expected_path, "r", encoding="utf-8") as expected_file:
        actual_text = normalize_text_for_similarity(actual_file.read())
        expected_text = normalize_text_for_similarity(expected_file.read())

    assert actual_text, f"Generated text file is empty: {actual_path}"
    assert expected_text, f"Canonical text file is empty: {expected_path}"

    min_len = min(len(actual_text), len(expected_text))
    max_len = max(len(actual_text), len(expected_text))
    length_ratio = min_len / max_len if max_len else 1.0
    similarity_ratio = difflib.SequenceMatcher(None, actual_text, expected_text).ratio()

    assert length_ratio >= min_length_ratio, (
        f"Text length drift too large for {actual_path}. "
        f"length_ratio={length_ratio:.3f}, expected>={min_length_ratio:.3f}"
    )
    assert similarity_ratio >= min_similarity_ratio, (
        f"Text similarity too low for {actual_path}. "
        f"similarity_ratio={similarity_ratio:.3f}, expected>={min_similarity_ratio:.3f}"
    )


def assert_pdf_matches(actual_path, expected_path):
    """Compare PDFs by page count. Text layer is OCR output already validated by test_06."""
    actual_reader = PdfReader(actual_path)
    expected_reader = PdfReader(expected_path)

    assert len(actual_reader.pages) == len(expected_reader.pages), (
        f"PDF {actual_path} does not match canonical page count: "
        f"got {len(actual_reader.pages)}, expected {len(expected_reader.pages)}."
    )


def assert_vtt_matches(actual_path, expected_path):
    """Compare VTT cue text while ignoring timing differences between runs."""
    timing_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}$")

    def extract_cue_text(path):
        with open(path, "r", encoding="utf-8") as file_handle:
            lines = [line.strip() for line in file_handle.read().replace("\r\n", "\n").split("\n")]

        return "\n".join(
            line for line in lines
            if line and line != "WEBVTT" and not timing_pattern.match(line)
        )

    actual_text = normalize_text_for_similarity(extract_cue_text(actual_path))
    expected_text = normalize_text_for_similarity(extract_cue_text(expected_path))

    min_len = min(len(actual_text), len(expected_text))
    max_len = max(len(actual_text), len(expected_text))
    length_ratio = min_len / max_len if max_len else 1.0
    similarity_ratio = difflib.SequenceMatcher(None, actual_text, expected_text).ratio()

    assert length_ratio >= 0.8, f"VTT length drift too large for {actual_path}. length_ratio={length_ratio:.3f}"
    assert similarity_ratio >= 0.4, f"VTT similarity too low for {actual_path}. similarity_ratio={similarity_ratio:.3f}"
