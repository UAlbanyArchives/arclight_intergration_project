import os
import time
import argparse
from iiiflow import collections, create_manifest

def main():
    parser = argparse.ArgumentParser(description="Update IIIF manifests.")
    parser.add_argument(
        "--collection-id",
        help="Limit to a specific collection ID (e.g., apap101)",
        default=None,
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=25.0,
        help="Maximum age of manifest in hours before regenerating (default: 25)",
    )
    parser.add_argument(
        "--toc",
        action="store_true",
        help="Include IIIF table of contents from content.md headings when available.",
    )

    args = parser.parse_args()

    max_age_seconds = args.hours * 3600  # convert hours to seconds
    cutoff_time = time.time() - max_age_seconds

    for collection in collections:
        if args.collection_id and collection.id != args.collection_id:
            continue

        print(f"Processing collection: {collection.id}")
        for object_id in collection.objects:
            object_path = os.path.join(collection.path, object_id)
            manifest_path = os.path.join(object_path, "manifest.json")
            metadata_path = os.path.join(object_path, "metadata.yml")

            should_create = (
                not os.path.isfile(manifest_path) or
                os.path.getmtime(manifest_path) < cutoff_time
            )

            if should_create and os.path.isfile(metadata_path):
                print(f"Creating manifest for {object_id}")
                create_manifest(collection.id, object_id, toc=args.toc)
