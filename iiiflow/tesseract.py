import os
import re
import time
import json
import zipfile
import urllib.parse
import yaml
import traceback
from PIL import Image
from PIL import ImageOps
from subprocess import Popen, PIPE
from bs4 import BeautifulSoup
from warcio.archiveiterator import ArchiveIterator
from .utils import check_no_image_type
from .utils import validate_config_and_paths

ALLOWED_AUTOMATED_TEXT_TOOLS = {"tesseract"}
HTML_MIME_TYPES = ("text/html", "application/xhtml", "application/xhtml+xml")


def _prepare_image_for_ocr(img_path, temp_dir):
    """
    Normalize source images to an OCR-safe JPEG input.
    """
    os.makedirs(temp_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(img_path))[0]
    normalized_path = os.path.join(temp_dir, f"{base_name}_ocr.jpg")

    with Image.open(img_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(normalized_path, format="JPEG", quality=90)

    return normalized_path


def _run_tesseract_ocr(tesseract_cmd):
    process = Popen(tesseract_cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr


def _normalize_page_url(url):
    return (url or "").strip().rstrip("/")


def _apply_replay_url_filter(records, metadata):
    replay_url = metadata.get("replay_url")
    target_page_urls = []

    if replay_url:
        if isinstance(replay_url, list):
            target_page_urls = [_normalize_page_url(url) for url in replay_url if url]
        else:
            normalized = _normalize_page_url(replay_url)
            if normalized:
                target_page_urls = [normalized]

    if not target_page_urls:
        return records

    return [record for record in records if _normalize_page_url(record.get("url")) in target_page_urls]


def _html_to_text(html_bytes):
    if not html_bytes:
        return ""
    soup = BeautifulSoup(html_bytes, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _read_warc_text_records_from_stream(stream):
    records = []
    for record in ArchiveIterator(stream):
        if record.rec_type != "response":
            continue

        url = record.rec_headers.get_header("WARC-Target-URI")
        if not url or not url.startswith("http"):
            continue

        if record.http_headers:
            status = record.http_headers.get_statuscode()
            if not status.startswith("2"):
                continue
            content_type = record.http_headers.get_header("Content-Type") or ""
        else:
            content_type = record.rec_headers.get_header("Content-Type") or ""

        mime = content_type.split(";")[0].strip().lower()
        if mime not in HTML_MIME_TYPES:
            continue

        html_bytes = record.content_stream().read()
        page_text = _html_to_text(html_bytes)
        if page_text:
            records.append({"url": url, "text": page_text})

    return records


def _read_warc_text_records(warc_path):
    with open(warc_path, "rb") as stream:
        return _read_warc_text_records_from_stream(stream)


def _read_wacz_text_records(wacz_path):
    records = []

    with zipfile.ZipFile(wacz_path, "r") as zf:
        for member_name in sorted(zf.namelist()):
            lower_name = member_name.lower()
            if not lower_name.startswith("archive/"):
                continue
            if not (lower_name.endswith(".warc") or lower_name.endswith(".warc.gz")):
                continue

            with zf.open(member_name) as stream:
                records.extend(_read_warc_text_records_from_stream(stream))

        page_urls = []
        if "pages/pages.jsonl" in zf.namelist():
            raw = zf.read("pages/pages.jsonl").decode("utf-8", errors="replace")
            for line in raw.strip().splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = entry.get("url")
                if url:
                    page_urls.append(_normalize_page_url(url))

        if page_urls:
            page_set = set(page_urls)
            records = [record for record in records if _normalize_page_url(record.get("url")) in page_set]

    return records


def _slug_from_url(url):
    parsed = urllib.parse.urlparse(url or "")
    candidate = parsed.path.strip("/").split("/")[-1] if parsed.path else ""
    if not candidate:
        candidate = parsed.netloc or "page"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", candidate).strip("_")
    return slug[:60] or "page"


def _extract_web_archive_text(object_path, metadata):
    txt_dir = os.path.join(object_path, "txt")
    content_file_path = os.path.join(object_path, "content.txt")
    os.makedirs(txt_dir, exist_ok=True)

    records = []

    wacz_dir = os.path.join(object_path, "wacz")
    warc_dir = os.path.join(object_path, "warc.gz")

    if os.path.isdir(wacz_dir):
        wacz_files = [f for f in sorted(os.listdir(wacz_dir)) if f.lower().endswith(".wacz")]
        if wacz_files:
            records = _read_wacz_text_records(os.path.join(wacz_dir, wacz_files[0]))
    elif os.path.isdir(warc_dir):
        warc_files = [
            f for f in sorted(os.listdir(warc_dir))
            if f.lower().endswith(".warc") or f.lower().endswith(".warc.gz")
        ]
        if warc_files:
            records = _read_warc_text_records(os.path.join(warc_dir, warc_files[0]))

    records = _apply_replay_url_filter(records, metadata)

    pages_written = 0
    with open(content_file_path, "w", encoding="utf-8") as content_file:
        for index, record in enumerate(records, start=1):
            page_text = (record.get("text") or "").strip()
            if not page_text:
                continue

            page_slug = _slug_from_url(record.get("url"))
            txt_filename = f"page_{index:04d}_{page_slug}.txt"
            txt_filepath = os.path.join(txt_dir, txt_filename)

            with open(txt_filepath, "w", encoding="utf-8") as txt_file:
                txt_file.write(page_text + "\n")

            content_file.write(page_text + "\n")
            pages_written += 1

    if pages_written == 0:
        print(f"No HTML pages were extracted from web archive in {object_path}.")
    else:
        print(f"Extracted text from {pages_written} web archive pages in {object_path}.")

    return pages_written

def create_hocr(collection_id, object_id, config_path="~/.iiiflow.yml"):
    """
    Processes images in a given collection and object directory with Tesseract OCR,
    creating HOCR and TXT files for the images, as well as content.txt
    Designed to be used with the discovery storage specification
    https://github.com/UAlbanyArchives/arclight_integration_project/blob/main/discovery_storage_spec.md

    Args:
        collection_id (str): The collection ID.
        object_id (str): The object ID.
        config_path (str): Path to the configuration YAML file.
    """
    
    # Read config and validate paths
    discovery_storage_root, log_file_path, object_path = validate_config_and_paths(
        config_path, collection_id, object_id
    )

    img_dir = os.path.join(object_path, "jpg")
    ocr_dir = os.path.join(object_path, "hocr")
    txt_dir = os.path.join(object_path, "txt")
    metadata_path = os.path.join(object_path, "metadata.yml")

    metadata = {}
    if os.path.isfile(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as metadata_file:
            metadata = yaml.safe_load(metadata_file) or {}

    automated_text_tool = metadata.get("automated_text_tool")
    automated_text_tool_normalized = str(automated_text_tool).strip().lower() if automated_text_tool is not None else ""
    if automated_text_tool is not None and automated_text_tool_normalized not in ALLOWED_AUTOMATED_TEXT_TOOLS:
        print(
            f"Skipping OCR for {collection_id}/{object_id}: "
            f"automated_text_tool='{automated_text_tool_normalized}' is not permitted for tesseract."
        )
        return

    print(f"Processing {collection_id}/{object_id}...")

    resource_type = str(metadata.get("resource_type", "")).strip().lower()
    if resource_type == "web archive":
        pages_written = _extract_web_archive_text(object_path, metadata)
        if pages_written > 0 and metadata_path and os.path.isfile(metadata_path):
            metadata["automated_text_tool"] = "tesseract"
            with open(metadata_path, "w", encoding="utf-8") as metadata_file:
                yaml.safe_dump(metadata, metadata_file, sort_keys=False)
        return

    # if theres no jpg, look for other images
    if not os.path.isdir(img_dir):
        for folder in ["jpeg", "png", "tif"]:
            img_dir = os.path.join(object_path, folder)
            if os.path.isdir(img_dir):
                break
        else:
            if not check_no_image_type:
                raise ValueError(f"ERROR: Could not find valid image folder in {object_path}.")

    if os.path.isdir(img_dir):

        # Ensure the output directories exist
        os.makedirs(ocr_dir, exist_ok=True)
        os.makedirs(txt_dir, exist_ok=True)

        # Aggregate all text files into a single content.txt file
        content_file_path = os.path.join(object_path, "content.txt")
        temp_ocr_dir = os.path.join(object_path, "_tmp_ocr")
        temp_normalized_inputs = []
        failed_pages = []
        with open(content_file_path, "w", encoding="utf-8") as content_file:
            for filename in sorted(os.listdir(img_dir)):
                if filename.lower().endswith((".jpg", ".jpeg", ".png", ".tif")):
                    img_filepath = os.path.join(img_dir, filename)
                    base_filename = os.path.splitext(filename)[0]

                    hocr_filepath = os.path.join(ocr_dir, f"{base_filename}")
                    txt_filepath = os.path.join(txt_dir, f"{base_filename}.txt")
                    print ("\t" + f"Processing {filename}...")

                    tesseract_cmd = [
                        "tesseract",
                        img_filepath,
                        hocr_filepath,
                        '-c', 'tessedit_create_hocr=1',
                        '-c', 'tessedit_create_txt=1',
                        "--dpi", "300"
                    ]
                    generated_txt_path = hocr_filepath + ".txt"
                    
                    try:
                        # First try OCR on the original input to preserve canonical text similarity.
                        returncode, stdout, stderr = _run_tesseract_ocr(tesseract_cmd)
                        used_input_path = img_filepath

                        # If the original input fails, retry once with a normalized JPEG.
                        if returncode != 0:
                            normalized_input_path = _prepare_image_for_ocr(img_filepath, temp_ocr_dir)
                            temp_normalized_inputs.append(normalized_input_path)
                            tesseract_cmd[1] = normalized_input_path
                            returncode, stdout, stderr = _run_tesseract_ocr(tesseract_cmd)
                            used_input_path = normalized_input_path

                        if returncode != 0:
                            stdout_text = stdout.decode("utf-8", errors="replace")
                            stderr_text = stderr.decode("utf-8", errors="replace")
                            message = (
                                f"Tesseract OCR failed for {filename}. Continuing to next image.\n"
                                f"Command: {' '.join(tesseract_cmd)}\n"
                                f"Return code: {returncode}\n"
                                f"Input image: {used_input_path}\n"
                                f"Output base: {hocr_filepath}\n"
                                f"STDOUT: {stdout_text}\n"
                                f"STDERR: {stderr_text}"
                            )
                            print(message)
                            failed_pages.append(filename)
                            if used_input_path in temp_normalized_inputs:
                                temp_normalized_inputs.remove(used_input_path)
                            with open(log_file_path, "a", encoding="utf-8") as log:
                                log.write("\n" + message + "\n")
                            continue

                        # Move the generated .txt file to the txt directory
                        if not os.path.isfile(generated_txt_path):
                            message = (
                                f"Tesseract OCR produced no text output for {filename}. Continuing to next image.\n"
                                f"Expected TXT path: {generated_txt_path}\n"
                                f"Input image: {used_input_path}"
                            )
                            print(message)
                            failed_pages.append(filename)
                            if used_input_path in temp_normalized_inputs:
                                temp_normalized_inputs.remove(used_input_path)
                            with open(log_file_path, "a", encoding="utf-8") as log:
                                log.write("\n" + message + "\n")
                            continue
                        else:
                            os.replace(generated_txt_path, txt_filepath)

                        # Append text content to content.txt
                        if os.path.isfile(txt_filepath):
                            with open(txt_filepath, "r", encoding="utf-8") as txt_file:
                                content_file.write(txt_file.read())
                                content_file.write("\n")

                        if used_input_path in temp_normalized_inputs:
                            temp_normalized_inputs.remove(used_input_path)
                            os.remove(used_input_path)

                    except Exception as e:
                        failed_pages.append(filename)
                        print(f"Unexpected OCR error for {filename}. Continuing to next image. See log: {log_file_path}")
                        with open(log_file_path, "a", encoding="utf-8") as log:
                            log.write(f"\nERROR processing {img_filepath} with Tesseract:\n")
                            log.write(traceback.format_exc())

        if failed_pages:
            print(f"OCR failed for {len(failed_pages)} page(s): {failed_pages}")

        for temp_path in temp_normalized_inputs:
            if os.path.isfile(temp_path):
                os.remove(temp_path)

        if os.path.isdir(temp_ocr_dir) and not os.listdir(temp_ocr_dir):
            os.rmdir(temp_ocr_dir)

    print(f"Completed processing for collection {collection_id}.")

    if metadata_path and os.path.isfile(metadata_path):
        metadata["automated_text_tool"] = "tesseract"
        with open(metadata_path, "w", encoding="utf-8") as metadata_file:
            yaml.safe_dump(metadata, metadata_file, sort_keys=False)
