import os
import yaml
import shutil
import traceback
from PIL import Image
from PIL import ImageOps
from pypdf import PdfMerger
from subprocess import Popen, PIPE
from .utils import check_no_image_type
from .utils import validate_config_and_paths

def resize_image(img_path, max_size=1500):
    """
    Resizes an image while maintaining aspect ratio, ensuring the longest side is at most `max_size`.
    Converts PNG images to JPEG for smaller file size.

    Args:
        img_path (str): Path to the image.
        max_size (int): Maximum size for the longest side.

    Returns:
        str: Path to the resized image (saved as a temporary file).
    """
    # Extract filename and extension
    base, ext = os.path.splitext(img_path)
    ext = ext.lower()

    # Set new filename with _resized
    resized_img_path = f"{base}_resized.jpg"  # Always save as JPG

    with Image.open(img_path) as img:
        # Apply EXIF orientation so saved output is physically upright.
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_size, max_size), Image.LANCZOS)

        # Normalize every image to RGB before JPEG export for OCR stability.
        if img.mode != "RGB":
            img = img.convert("RGB")

        img.save(resized_img_path, format="JPEG", quality=85)  # Save with reduced quality to further reduce size

    return resized_img_path

def create_pdf(collection_id, object_id, config_path="~/.iiiflow.yml"):
    """
    Converts images in a given collection and object directory to a PDF.
    Designed to be used with the discovery storage specification
    https://github.com/UAlbanyArchives/arclight_integration_project/blob/main/discovery_storage_spec.md

    Args:
        collection_id (str): The collection ID.
        object_id (str): The object ID.
        config_path (str): Path to the configuration YAML file.
    """

    img_priorities = ("png", "jpg", "jpeg", "tif", "tiff")

    # Read config and validate paths
    discovery_storage_root, log_file_path, object_path = validate_config_and_paths(
        config_path, collection_id, object_id
    )

    metadata_path = os.path.join(object_path, "metadata.yml")
    metadata = {}
    if os.path.isfile(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as metadata_file:
            metadata = yaml.safe_load(metadata_file) or {}

    original_file_legacy = metadata.get("original_file_legacy", "")
    original_ext = os.path.splitext(original_file_legacy)[1].lower() if isinstance(original_file_legacy, str) else ""
    if original_ext == ".pdf":
        print(
            f"Skipping PDF creation for {collection_id}/{object_id}: "
            f"original_file_legacy is already a PDF ({original_file_legacy})."
        )
        return

    img_dir = None
    for folder in img_priorities:
        img_dir = os.path.join(object_path, folder)
        if os.path.isdir(img_dir):
            break
    if img_dir is None:
        if check_no_image_type:
            print ("Cannot create PDF. Object is A/V or dataset.")
        else:
            raise ValueError(f"ERROR: Could not find valid image folder in {object_path}.")
            
    pdf_path = os.path.join(object_path, "pdf")
    os.makedirs(pdf_path, exist_ok=True)

    # List of PDFs to merge
    pdf_files_to_merge = []

    # Sort images for correct order
    image_files = sorted(
        [f for f in os.listdir(img_dir) if f.lower().endswith(img_priorities)]
    )

    temp_resized_files = []  # Store resized images for cleanup
    failed_pages = []

    for img in image_files:
        print(f"\tConverting {img} to searchable PDF...")
        img_path = os.path.join(img_dir, img)

        # reduce image size
        resized_img_path = resize_image(img_path, max_size=1500)
        temp_resized_files.append(resized_img_path)  # Store for cleanup

        # Generate a searchable PDF from the image using Tesseract
        img_stem, _ = os.path.splitext(img)
        temp_pdf_path = os.path.join(pdf_path, f"{img_stem}.pdf")
        tesseract_output_base = os.path.splitext(temp_pdf_path)[0]
        tesseract_cmd = ["tesseract", resized_img_path, tesseract_output_base, "pdf"]
        
        process = Popen(tesseract_cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            print(
                f"Tesseract OCR failed for {img}. Continuing to next image.\n"
                f"Command: {' '.join(tesseract_cmd)}\n"
                f"Return code: {process.returncode}\n"
                f"Input image: {resized_img_path}\n"
                f"Output base: {tesseract_output_base}\n"
                f"STDOUT: {stdout_text}\n"
                f"STDERR: {stderr_text}"
            )
            failed_pages.append(img)
            if resized_img_path in temp_resized_files:
                temp_resized_files.remove(resized_img_path)
            continue

        # Append the individual searchable PDF to the list
        pdf_files_to_merge.append(temp_pdf_path)

    if failed_pages:
        print(f"OCR failed for {len(failed_pages)} page(s): {failed_pages}")

    if not pdf_files_to_merge:
        raise RuntimeError("OCR processing failed for all images; no PDF pages were generated.")

    # Merge all the individual PDFs into one
    final_pdf_path = os.path.join(pdf_path, "binder.pdf")
    pdf_merger = PdfMerger()

    for pdf in pdf_files_to_merge:
        pdf_merger.append(pdf)

    # Write the final combined PDF
    pdf_merger.write(final_pdf_path)
    pdf_merger.close()

    # Cleanup: Remove individual PDFs
    print("Cleaning up temporary files...")
    for temp_img in temp_resized_files:
        os.remove(temp_img)
    for pdf in pdf_files_to_merge:
        os.remove(pdf)

    print(f"Searchable PDF successfully created: {final_pdf_path}")
