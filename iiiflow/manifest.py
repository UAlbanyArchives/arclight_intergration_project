import os
import yaml
import json
import re
from iiif_prezi3 import config
from .utils import validate_config_and_paths, remove_nulls
from .manifest_builders import (
    create_iiif_manifest as _create_iiif_manifest,
    create_iiif_canvas as _create_iiif_canvas,
    build_manifest_label,
    resolve_resource_source,
    thumbnail_data,
)


def create_iiif_canvas(*args, **kwargs):
    """Compatibility wrapper retained for external callers."""
    return _create_iiif_canvas(*args, **kwargs)


def create_iiif_manifest(*args, **kwargs):
    """Compatibility wrapper retained for external callers."""
    return _create_iiif_manifest(*args, **kwargs)


def _canvas_id_by_filename(manifest_dict):
    canvas_ids = {}

    def register_alias(name, canvas_id):
        if not isinstance(name, str):
            return

        normalized = os.path.basename(name.strip()).lower()
        if not normalized:
            return

        canvas_ids.setdefault(normalized, canvas_id)
        stem, _ext = os.path.splitext(normalized)
        if stem:
            canvas_ids.setdefault(stem, canvas_id)

    for canvas in manifest_dict.get("items", []):
        canvas_id = canvas.get("id")
        if not canvas_id:
            continue

        label = canvas.get("label")
        if isinstance(label, str):
            register_alias(label, canvas_id)
            continue

        if not isinstance(label, dict):
            continue

        for label_values in label.values():
            if isinstance(label_values, list):
                for value in label_values:
                    if isinstance(value, str):
                        register_alias(value, canvas_id)
            elif isinstance(label_values, str):
                register_alias(label_values, canvas_id)

    return canvas_ids


def _build_toc_structures(object_path, obj_url_root, manifest_dict, lang_code):
    content_path = os.path.join(object_path, "content.md")
    if not os.path.isfile(content_path):
        return None

    filename_to_canvas = _canvas_id_by_filename(manifest_dict)

    with open(content_path, "r", encoding="utf-8") as content_file:
        content_lines = content_file.readlines()

    file_marker_pattern = re.compile(r"^\s*<!--\s*file:\s*([^>]+?)\s*-->\s*$")
    heading_pattern = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")

    top_range = {
        "id": f"{obj_url_root}/range/toc",
        "type": "Range",
        "behavior": ["top"],
        "label": {lang_code: ["Table of Contents"]},
        "items": [],
    }

    current_file = None
    range_counter = 0
    # Track open heading levels to preserve Markdown heading hierarchy.
    range_stack = [{"level": 0, "range": top_range}]

    for raw_line in content_lines:
        file_match = file_marker_pattern.match(raw_line)
        if file_match:
            current_file = file_match.group(1).strip()
            continue

        heading_match = heading_pattern.match(raw_line)
        if not heading_match or not current_file:
            continue

        marker = os.path.basename(current_file.strip()).lower()
        marker_stem, _marker_ext = os.path.splitext(marker)
        canvas_id = filename_to_canvas.get(marker) or filename_to_canvas.get(marker_stem)
        if not canvas_id:
            continue

        heading_level = len(heading_match.group(1))
        heading_text = heading_match.group(2).strip()
        if not heading_text:
            continue

        range_counter += 1
        heading_range = {
            "id": f"{obj_url_root}/range/toc/{range_counter}",
            "type": "Range",
            "label": {lang_code: [heading_text]},
            "items": [
                {
                    "id": canvas_id,
                    "type": "Canvas",
                }
            ],
        }

        while range_stack and range_stack[-1]["level"] >= heading_level:
            range_stack.pop()

        range_stack[-1]["range"]["items"].append(heading_range)
        range_stack.append({"level": heading_level, "range": heading_range})

    if not top_range["items"]:
        return None

    return [top_range]


def create_manifest(collection_id, object_id, config_path="~/.iiiflow.yml", toc=False):
    """
    Creates a manifest.json compliant with the IIIF v3 Presentation API
    Designed to be used with the discovery storage specification.
    https://github.com/UAlbanyArchives/arclight_integration_project/blob/main/discovery_storage_spec.md

    Args:
        collection_id (str): The collection ID.
        object_id (str): The object ID.
        config_path (str): Path to the configuration YAML file.
    """

    discovery_storage_root, log_file_path, object_path, manifest_url_root, image_api_root, provider, lang_code = validate_config_and_paths(
        config_path, collection_id, object_id, True, False, True, True
    )

    config.configs["helpers.auto_fields.AutoLang"].auto_lang = lang_code

    metadata_path = os.path.join(object_path, "metadata.yml")
    manifest_path = os.path.join(object_path, "manifest.json")
    with open(metadata_path, "r", encoding="utf-8") as yml_file:
        metadata = yaml.safe_load(yml_file)

    resource_type = metadata["resource_type"]
    files_path, resource_format = resolve_resource_source(object_path, resource_type)
    normalized_resource_type = (resource_type or "").strip().casefold()
    effective_resource_type = resource_type

    if normalized_resource_type == "video" and resource_format in {"ogg", "mp3"}:
        effective_resource_type = "Audio"

    if files_path and os.path.isdir(files_path):
        print(f"{collection_id}/{object_id}")

        obj_url_root = f"{manifest_url_root}/{collection_id}/{object_id}"
        iiif_url_root = f"{image_api_root}{collection_id}%2F{object_id}%2F{resource_format}"

        manifest_label = build_manifest_label(metadata)
        thumb_data = thumbnail_data(object_path, obj_url_root)

        iiif_manifest = _create_iiif_manifest(
            files_path,
            manifest_url_root,
            obj_url_root,
            iiif_url_root,
            resource_format,
            manifest_label,
            metadata,
            thumb_data,
            effective_resource_type,
            lang_code,
            config_path,
        )
        manifest_dict = iiif_manifest.dict()
        manifest_dict = remove_nulls(manifest_dict)

        provider_data = [
            {
                "id": manifest_url_root,
                "type": "Agent",
                "label": {lang_code: [provider]},
                "logo": [
                    {
                        "id": f"{manifest_url_root}/logo.png",
                        "type": "Image",
                        "format": "image/png"
                    }
                ]
            }
        ]

        manifest_output = {
            "@context": "http://iiif.io/api/presentation/3/context.json",
            "provider": provider_data,
            **manifest_dict
        }

        if toc:
            structures = _build_toc_structures(object_path, obj_url_root, manifest_dict, lang_code)
            if structures:
                manifest_output["structures"] = structures

        with open(manifest_path, "w") as file_handle:
            json.dump(manifest_output, file_handle, indent=2)

        print("\t --> IIIF manifest created successfully!")
    else:
        print(f"\tERROR: no path found {files_path}")
