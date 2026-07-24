import os
from PIL import Image
from iiif_prezi3 import KeyValueString

ORG_TEXT = "M.E. Grenander Department of Special Collections and Archives, University Libraries, University at Albany, State University of New York"


def build_rights_and_attribution(metadata):
    attribution_statement = ORG_TEXT
    rights = None

    if "license" in metadata and metadata["license"] and metadata["license"].lower().strip() != "unknown":
        rights = metadata["license"]
        if "/publicdomain/" in rights:
            attribution_statement = (
                f"<span>This object is in the public domain, but you are encouraged to attribute: <br/> {ORG_TEXT} <br/> "
                f"<a href=\"{rights}\" title=\"Public Domain\"><img src=\"https://licensebuttons.net/p/88x31.png\"/></a></span>"
            )
        elif "/by-nc-nd/" in rights:
            attribution_statement = (
                f"<span>{ORG_TEXT} <br/> "
                f"<a href=\"{rights}\" title=\"CC BY-NC-ND 4.0\"><img src=\"https://licensebuttons.net/l/by-nc-nd/4.0/88x31.png\"/></a></span>"
            )
        elif "/by-nc-sa/" in rights:
            attribution_statement = (
                f"<span>{ORG_TEXT} <br/> "
                f"<a href=\"{rights}\" title=\"CC BY-NC-SA 4.0\"><img src=\"https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png\"/></a></span>"
            )
        elif "/by/" in rights:
            attribution_statement = (
                f"<span>{ORG_TEXT} <br/> "
                f"<a href=\"{rights}\" title=\"CC BY 4.0\"><img src=\"https://licensebuttons.net/l/by/4.0/88x31.png\"/></a></span>"
            )
    elif "rights_statement" in metadata and metadata["rights_statement"]:
        rights = metadata["rights_statement"]
        if "InC-EDU" in rights:
            rights = "https://rightsstatements.org/vocab/InC-EDU/1.0/"
            stmt = "In Copyright - Educational Use Permitted"
            attribution_statement = (
                f"<span>{ORG_TEXT} <br/> "
                f"<a href=\"{rights}\" title=\"{stmt}\"><img src=\"https://rightsstatements.org/files/buttons/InC-EDU.dark.svg\"/></a></span>"
            )
    else:
        rights = "https://rightsstatements.org/vocab/InC-EDU/1.0/"
        stmt = "In Copyright - Educational Use Permitted"
        attribution_statement = (
            f"<span>{ORG_TEXT} <br/> "
            f"<a href=\"{rights}\" title=\"{stmt}\"><img src=\"https://rightsstatements.org/files/buttons/InC-EDU.dark.svg\"/></a></span>"
        )

    return rights, attribution_statement


def build_required_statement(lang_code, attribution_statement):
    return KeyValueString(
        label={lang_code: ["Attribution"]},
        value={lang_code: [attribution_statement]}
    )


def build_manifest_label(metadata):
    if "manifest_label" in metadata.keys():
        return metadata["manifest_label"].strip()

    if "title" in metadata and metadata["title"]:
        manifest_label = metadata["title"].strip()
        if "date_display" in metadata and metadata["date_display"]:
            manifest_label += f", {metadata['date_display'].strip()}"
        return manifest_label

    for key in ["original_file", "original_file_legacy", "resource_type"]:
        if key in metadata and metadata[key]:
            return metadata[key].strip()

    return "Untitled"


def resolve_resource_source(object_path, resource_type):
    normalized_resource_type = (resource_type or "").strip().casefold()

    if normalized_resource_type == "audio":
        ogg_path = os.path.join(object_path, "ogg")
        mp3_path = os.path.join(object_path, "mp3")
        if os.path.isdir(ogg_path) and len(os.listdir(ogg_path)) > 0:
            return ogg_path, "ogg"
        if os.path.isdir(mp3_path) and len(os.listdir(mp3_path)) > 0:
            return mp3_path, "mp3"
        return None, None

    if normalized_resource_type == "video":
        # Prefer video derivatives, but gracefully fall back to audio-only derivatives.
        video_formats = ["webm", "mp4", "mov", "mpeg", "avi"]
        for fmt in video_formats:
            candidate_path = os.path.join(object_path, fmt)
            if os.path.isdir(candidate_path) and len(os.listdir(candidate_path)) > 0:
                return candidate_path, fmt

        for fmt in ["ogg", "mp3"]:
            candidate_path = os.path.join(object_path, fmt)
            if os.path.isdir(candidate_path) and len(os.listdir(candidate_path)) > 0:
                return candidate_path, fmt

        return None, None

    if normalized_resource_type in {"web archive", "email"}:
        wacz_path = os.path.join(object_path, "wacz")
        if os.path.isdir(wacz_path):
            return wacz_path, "wacz"
        warc_path = os.path.join(object_path, "warc.gz")
        if os.path.isdir(warc_path):
            return warc_path, "warc.gz"
        # Email objects can also be represented as image derivatives.
        jpg_path = os.path.join(object_path, "jpg")
        if os.path.isdir(jpg_path):
            return jpg_path, "jpg"
        return None, None

    ptif_path = os.path.join(object_path, "ptif")
    if os.path.isdir(ptif_path):
        return ptif_path, "ptif"
    return os.path.join(object_path, "jpg"), "jpg"


def thumbnail_data(object_path, obj_url_root):
    thumbnail_path = os.path.join(object_path, "thumbnail.jpg")
    thumbnail_url = f"{obj_url_root}/thumbnail.jpg"

    try:
        with Image.open(thumbnail_path) as img:
            thumbnail_width, thumbnail_height = img.size
    except Exception as e:
        print(f"Error reading thumbnail image: {e}")
        thumbnail_width = None
        thumbnail_height = None

    return {"url": thumbnail_url, "width": thumbnail_width, "height": thumbnail_height}
