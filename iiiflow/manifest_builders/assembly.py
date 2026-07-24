import os
import urllib.parse
from iiif_prezi3 import Manifest
from iiiflow.metadata import update_metadata_fields
from ..utils import get_image_dimensions
from .canvas import create_iiif_canvas
from .renderings import append_manifest_renderings
from .services import attach_search_service_if_configured
from .policies import build_rights_and_attribution, build_required_statement
from .web_archive import create_web_archive_canvases


def create_iiif_manifest(
    file_dir,
    manifest_url_root,
    obj_url_root,
    iiif_url_root,
    resource_format,
    label,
    metadata,
    thumbnail_data,
    resource_type,
    lang_code,
    config_path="~/.iiiflow.yml",
):
    behavior = ["individuals"]
    if "behavior" in metadata.keys():
        behavior = [metadata["behavior"]]

    rights, attribution_statement = build_rights_and_attribution(metadata)
    required_statement = build_required_statement(lang_code, attribution_statement)

    manifest = Manifest(
        id=f"{obj_url_root}/manifest.json",
        label=label,
        behavior=behavior,
        rights=rights,
        requiredStatement=required_statement,
    )

    manifest = update_metadata_fields(manifest, metadata, lang_code)
    normalized_resource_type = (resource_type or "").strip().casefold()

    if normalized_resource_type in {"web archive", "email"}:
        create_web_archive_canvases(manifest, file_dir, obj_url_root, thumbnail_data, lang_code, metadata)
    else:
        page_count = 0
        for resource_file in sorted(os.listdir(file_dir)):
            resource_path = os.path.join(file_dir, resource_file)
            filename = urllib.parse.quote(os.path.splitext(resource_file)[0])
            quoted_file = urllib.parse.quote(resource_file.strip())
            page_count += 1

            if normalized_resource_type in ["audio", "video"]:
                media_url = f"{obj_url_root}/{os.path.basename(file_dir)}/{quoted_file}"
                create_iiif_canvas(
                    manifest,
                    manifest_url_root,
                    obj_url_root,
                    resource_file,
                    resource_type.title(),
                    resource_path,
                    page_count,
                    thumbnail_data,
                    media_url=media_url,
                    filename=filename,
                    lang_code=lang_code,
                )
            elif resource_file.lower().endswith(resource_format.lower()):
                try:
                    img_width, img_height = get_image_dimensions(resource_path)
                except Exception as exc:
                    print(f"Skipping missing image {resource_path}: {exc}")
                    continue
                image_url = f"{iiif_url_root}%2F{quoted_file}"
                create_iiif_canvas(
                    manifest,
                    manifest_url_root,
                    obj_url_root,
                    resource_file,
                    "Image",
                    resource_path,
                    page_count,
                    thumbnail_data,
                    resource_format=resource_format,
                    height=img_height,
                    width=img_width,
                    image_url=image_url,
                    filename=filename,
                    lang_code=lang_code,
                )

    append_manifest_renderings(manifest, file_dir, obj_url_root, metadata)
    attach_search_service_if_configured(manifest, file_dir, manifest_url_root, obj_url_root, lang_code, config_path)

    return manifest
