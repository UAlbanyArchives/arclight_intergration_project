import os
import yaml
import json
import traceback
from iiif_prezi3 import Manifest
from .utils import validate_config_and_paths


def update_metadata_fields(manifest, metadata, lang_code="en"):
    """
    Updates the metadata and behavior fields of a IIIF manifest using values from a metadata dictionary.
    
    Args:
        manifest (dict or iiif_prezi3.Manifest): The IIIF manifest as a dictionary or Manifest object.
        metadata (dict): The loaded YAML metadata as a dictionary.
        lang_code (str, optional): The language code for metadata values (default is "en").
    
    Returns:
        dict or iiif_prezi3.Manifest: The updated manifest with new metadata and behavior fields.

    Notes:
        - Clears existing metadata from the manifest.
        - Adds new metadata fields from the metadata dictionary.
    """

    fields = [
        "legacy_id",
        "resource_type",
        "coverage",
        "preservation_package",
        "description",
        "subjects",
        "processing_activity",
        "creator",
        "contributor",
        "identifier",
        "source",
        "master_format",
        "date_digitized",
        "date_uploaded",
    ]

    # Create new metadata list
    new_metadata = []

    for field in fields:
        if field in metadata and metadata[field]:  
            value = metadata[field]

            # If value is a list (like subjects), keep it as a list of strings
            if isinstance(value, list):
                value_list = [str(v) for v in value if v]
            else:
                value_list = [str(value)]

            new_metadata.append({
                "label": {lang_code: [field]},
                "value": {lang_code: value_list}
            })

    # Handle both dict-based and iiif_prezi3 Manifest objects
    if isinstance(manifest, Manifest):
        manifest.metadata = new_metadata  
    elif isinstance(manifest, dict):
        manifest["metadata"] = new_metadata  
    else:
        raise TypeError("manifest must be a dict or an iiif_prezi3.Manifest object")

    return manifest


def validate_metadata(collection_id, object_id, config_path="~/.iiiflow.yml"):
    """
    Validates metadata.yml
    Designed to be used with the discovery storage specification
    https://github.com/UAlbanyArchives/arclight_integration_project/blob/main/discovery_storage_spec.md

    Args:
        collection_id (str): The collection ID.
        object_id (str): The object ID.
        config_path (str): Path to the configuration YAML file.

    Returns:
        valid (bool)
    """

    # Read config and validate paths
    discovery_storage_root, log_file_path, object_path = validate_config_and_paths(
        config_path, collection_id, object_id
    )

    metadata_path = os.path.join(object_path, "metadata.yml")
    if not os.path.isfile(metadata_path):
        print (f"Missing metadata file {metadata_path}.")
        return False

    try:
        with open(metadata_path, "r") as metadata_file:
            metadata = yaml.safe_load(metadata_file)
    except Exception as e:
        with open(log_file_path, "a") as log:
            log.write(f"\nERROR reading metadata.yml for {object_path}\n")
            log.write(traceback.format_exc())
        return False

    required_keys = [
        "resource_type",
        "license",
        "date_uploaded"
    ]
    min_length = 1
    for key in required_keys:
        if key not in metadata:
            raise KeyError(f"Missing required key: {key}")
        value = metadata[key]
        if not isinstance(value, str):
            raise TypeError(f"The value for key '{key}' must be a string, got {type(value).__name__}.")
        if len(value) < min_length:
            raise ValueError(f"The value for key '{key}' must be at least {min_length} characters long.")

    if "preservation_package" in metadata:
        value = metadata["preservation_package"]
        if not isinstance(value, str):
            raise TypeError(f"The value for key 'preservation_package' must be a string, got {type(value).__name__}.")
        if len(value) < min_length:
            raise ValueError("The value for key 'preservation_package' must be at least 1 characters long.")
    
    controlled_fields = {
        "coverage": ["whole", "part"],
        "license": [
            "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "https://creativecommons.org/licenses/by/4.0/",
            "https://creativecommons.org/publicdomain/mark/1.0/",
            "Unknown",
        ],
        "resource_type": [
            "Audio",
            "Bound Volume",
            "Dataset",
            "Document",
            "Image",
            "Map",
            "Mixed Materials",
            "Pamphlet",
            "Periodical",
            "Slides",
            "Video",
            "Web Archive",
            "Other",
        ],
        "behavior": [
            "unordered",
            "individuals",
            "continuous",
            "paged",
        ],
    }

    for field in controlled_fields.keys():
        if field in metadata.keys():
            if field == "resource_type":
                allowed_resource_types = {value.casefold() for value in controlled_fields[field]}
                if str(metadata[field]).casefold() not in allowed_resource_types:
                    raise ValueError(f"Invalid metadata.yml for {object_path}. Invalid controlled field {field} value {metadata[field]}.")
            elif metadata[field] not in controlled_fields[field]:
                raise ValueError(f"Invalid metadata.yml for {object_path}. Invalid controlled field {field} value {metadata[field]}.")

    rights_statement_variants = {
        "https://rightsstatements.org/vocab/inc-edu/1.0/"
    }
    if metadata["license"].strip().lower() == "unknown":
        rights_statement = metadata.get("rights_statement")
        if not rights_statement or not isinstance(rights_statement, str):
            raise ValueError(f"Invalid metadata.yml for {object_path}. Missing rights_statement with Unknown license.")

        normalized_rights_statement = rights_statement.strip().lower()
        if normalized_rights_statement not in rights_statement_variants:
            raise ValueError(f"Invalid metadata.yml for {object_path}. Missing or invalid rights_statement with Unknown license.")

    return True


def update_metadata(collection_id, object_id, config_path="~/.iiiflow.yml"):
    """
    Updates metadata in manifest.json from fields in metadata.yml.
    This also updates the behavior field in the manifest.
    Designed to be used with the discovery storage specification
    https://github.com/UAlbanyArchives/arclight_integration_project/blob/main/discovery_storage_spec.md

    Args:
        collection_id (str): The collection ID.
        object_id (str): The object ID.
        config_path (str): Path to the configuration YAML file.
    """

    # Read config and validate paths
    discovery_storage_root, log_file_path, object_path, lang_code = validate_config_and_paths(
        config_path, collection_id, object_id, False, False, False, True
    )

    metadata_path = os.path.join(object_path, "metadata.yml")
    if not os.path.isfile(metadata_path):
        with open(log_file_path, "a") as log:
            log.write(f"\nERROR: Missing metadata file {metadata_path}\n")
        raise FileNotFoundError(f"ERROR: Missing metadata file {metadata_path}.")
    manifest_path = os.path.join(object_path, "manifest.json")
    if not os.path.isfile(manifest_path):
        with open(log_file_path, "a") as log:
            log.write(f"\nERROR: Missing manifest {manifest_path}\n")
        raise FileNotFoundError(f"ERROR: Missing manifest {manifest_path}.")
    
    try:
        with open(metadata_path, "r") as metadata_file:
            metadata = yaml.safe_load(metadata_file)

        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
        except Exception as e:
            with open(log_file_path, "a") as log:
                log.write(f"\nERROR reading manifest.json for {object_path}\n")
                log.write(traceback.format_exc())
                print (traceback.format_exc())
                raise ValueError(f"ERROR: Error reading manifest {manifest_path}.")

        manifest = update_metadata_fields(manifest, metadata, lang_code)

        # set behavior
        if "behavior" in metadata:
            manifest["behavior"] = [metadata["behavior"]]

        # Save the updated manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print ("Manifest updated successfully!")

    except Exception as e:
        with open(log_file_path, "a") as log:
            log.write(f"\nERROR reading metadata.yml for {object_path}\n")
            log.write(traceback.format_exc())
            print (traceback.format_exc())
            raise ValueError(f"ERROR reading metadata.yml for {object_path}.")
