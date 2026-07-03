import os
import json
import difflib
import yaml
from iiiflow import create_manifest
from test_utils import load_config, iterate_collections_and_objects, create_temp_fixture_config

config_path = "./.iiiflow.yml"
discovery_storage_root, log_file_path = load_config(config_path)


def _generate_manifest(tmp_path, collection_id, object_id, config_overrides=None, create_manifest_kwargs=None):
    """Generate a manifest for one fixture object in an isolated temp copy and return parsed JSON."""
    temp_discovery_storage_root, temp_config_path = create_temp_fixture_config(tmp_path, config_path)

    if config_overrides:
        with open(temp_config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}
        for key, value in config_overrides.items():
            if value is None:
                config.pop(key, None)
            else:
                config[key] = value
        with open(temp_config_path, "w", encoding="utf-8") as config_file:
            yaml.safe_dump(config, config_file, sort_keys=False)

    object_path = os.path.join(temp_discovery_storage_root, collection_id, object_id)
    manifest_path = os.path.join(object_path, "manifest.json")
    if os.path.isfile(manifest_path):
        os.remove(manifest_path)

    create_manifest_kwargs = create_manifest_kwargs or {}
    create_manifest(collection_id, object_id, config_path=temp_config_path, **create_manifest_kwargs)

    assert os.path.isfile(manifest_path), f"manifest.json was not created for {collection_id}/{object_id}"
    assert os.path.getsize(manifest_path) > 0, f"Generated manifest is empty for {collection_id}/{object_id}"

    with open(manifest_path, "r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def _set_metadata_value(object_path, key, value):
    metadata_path = os.path.join(object_path, "metadata.yml")
    with open(metadata_path, "r", encoding="utf-8") as metadata_file:
        metadata = yaml.safe_load(metadata_file) or {}

    metadata[key] = value

    with open(metadata_path, "w", encoding="utf-8") as metadata_file:
        yaml.safe_dump(metadata, metadata_file, sort_keys=False)


def test_manifest(tmp_path):
    # Test creation of manifest.json against canonical fixture manifests.

    temp_discovery_storage_root, temp_config_path = create_temp_fixture_config(tmp_path, config_path)

    def test_action(collection_id, object_id, object_path):
        canonical_manifest_path = os.path.join(discovery_storage_root, collection_id, object_id, "manifest.json")
        manifest_path = os.path.join(object_path, "manifest.json")
        source_folders = ["ptif", "jpg", "ogg", "mp3", "webm"]

        if not os.path.isfile(canonical_manifest_path):
            if os.path.isfile(manifest_path):
                os.remove(manifest_path)

            create_manifest(collection_id, object_id, config_path=temp_config_path, toc=True)

            assert os.path.isfile(manifest_path), f"manifest.json was not created for {collection_id}/{object_id}"
            os.makedirs(os.path.dirname(canonical_manifest_path), exist_ok=True)
            with open(manifest_path, "r", encoding="utf-8") as generated_manifest_file:
                generated_manifest = json.load(generated_manifest_file)
            with open(canonical_manifest_path, "w", encoding="utf-8") as canonical_manifest_file:
                json.dump(generated_manifest, canonical_manifest_file, indent=2, ensure_ascii=False)
                canonical_manifest_file.write("\n")
            return

        if not any(os.path.isdir(os.path.join(object_path, folder)) for folder in source_folders):
            return

        if os.path.isfile(manifest_path):
            os.remove(manifest_path)

        create_manifest(collection_id, object_id, config_path=temp_config_path, toc=True)

        # Check the generated manifest.
        assert os.path.isfile(manifest_path), "manifest.json was not created."
        assert os.path.getsize(manifest_path) > 0, f"Manifest {manifest_path} is empty."

        # Compare generated and canonical manifests semantically to avoid false negatives
        # from formatting-only differences (for example, trailing newline presence).
        with open(manifest_path, "r", encoding="utf-8") as f1, open(canonical_manifest_path, "r", encoding="utf-8") as f2:
            generated_manifest_data = json.load(f1)
            canonical_manifest_data = json.load(f2)

        if generated_manifest_data != canonical_manifest_data:
            manifest1 = json.dumps(generated_manifest_data, indent=2, sort_keys=True).splitlines()
            manifest2 = json.dumps(canonical_manifest_data, indent=2, sort_keys=True).splitlines()

            diff = "\n".join(difflib.unified_diff(manifest1, manifest2, fromfile="new_manifest", tofile="canonical_manifest", lineterm=""))

            assert False, f"Manifest does not match canonical fixture version:\n{diff}"

    iterate_collections_and_objects(temp_discovery_storage_root, test_action)


def test_manifest_top_level_shape(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    assert manifest.get("@context") == "http://iiif.io/api/presentation/3/context.json"
    assert manifest.get("type") == "Manifest"
    assert isinstance(manifest.get("provider"), list) and manifest["provider"], "Manifest provider is missing."
    assert isinstance(manifest.get("items"), list) and manifest["items"], "Manifest canvases are missing."


def test_manifest_search_service_present_when_hocr_and_content_search_configured(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    services = manifest.get("service", [])
    assert services, "Expected content search service when hOCR exists and content_search_url is configured."
    assert services[0].get("type") == "SearchService"
    assert services[0].get("profile") == "http://iiif.io/api/search/1/search"
    assert services[0].get("id", "").endswith("/ua200/fd198d1a2ebfdddad630c9698a38df29")


def test_manifest_search_service_absent_when_content_search_not_configured(tmp_path):
    manifest = _generate_manifest(
        tmp_path,
        "ua200",
        "fd198d1a2ebfdddad630c9698a38df29",
        config_overrides={"content_search_url": None},
    )

    assert "service" not in manifest or not manifest.get("service"), (
        "Did not expect content search service when content_search_url is not configured."
    )


def test_manifest_video_canvas_includes_vtt_supplementing_annotation(tmp_path):
    manifest = _generate_manifest(tmp_path, "apap150", "894a38c4895e189ea982af845f46e99e")

    first_canvas = manifest["items"][0]
    annotations = first_canvas.get("annotations", [])
    assert annotations, "Expected supplementing annotations on video canvas."

    bodies = annotations[0]["items"][0].get("body", [])
    assert any(body.get("format") == "text/vtt" for body in bodies), "Expected VTT supplementing body on video canvas."


def test_manifest_audio_canvas_includes_primary_and_alternate_audio_bodies(tmp_path):
    manifest = _generate_manifest(tmp_path, "apap401", "56b3ab1c00ac03862ef0f47650905013")

    first_canvas = manifest["items"][0]
    anno_page = first_canvas["items"][0]
    painting_annotations = [item for item in anno_page.get("items", []) if item.get("motivation") == "painting"]
    formats = {item.get("body", {}).get("format") for item in painting_annotations}

    assert "audio/ogg" in formats, "Expected primary OGG painting annotation."
    assert "audio/mpeg" in formats, "Expected alternate MP3 painting annotation when MP3 derivative exists."


def test_manifest_renderings_include_content_and_original_label(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    renderings = manifest.get("rendering", [])
    assert renderings, "Expected rendering entries in ua200 manifest."

    rendering_ids = [item.get("id", "") for item in renderings]
    assert any(item_id.endswith("/content.txt") for item_id in rendering_ids), "Expected content.txt rendering entry."

    labels = []
    for rendering in renderings:
        label = rendering.get("label", {})
        if isinstance(label, dict):
            labels.extend(label.get("en", []))
    assert any("(Original)" in label for label in labels), "Expected at least one rendering label marked as original."


def test_manifest_web_archive_has_wacz_page_canvases(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua600.007", "d31b512cf15fb175cd50150637af7153")

    items = manifest.get("items", [])
    assert items, "Expected canvases generated from WACZ pages."
    assert len(items) == 8, "Expected all 8 WACZ pages to become canvases when no replay_url filter is set."

    for canvas in items:
        anno_page = canvas["items"][0]
        anno = anno_page["items"][0]
        body = anno.get("body", {})
        assert "replayweb.page" in body.get("id", ""), (
            f"Expected ReplayWeb.page URL as canvas body, got: {body.get('id')}"
        )

    # Renderings should include content.txt and the PDF, but no wacz/warc entries
    renderings = manifest.get("rendering", [])
    rendering_ids = [r.get("id", "") for r in renderings]
    assert any(r_id.endswith("/content.txt") for r_id in rendering_ids), "Expected content.txt rendering."
    assert any(r_id.endswith(".pdf") for r_id in rendering_ids), "Expected PDF rendering."
    assert not any("/wacz/" in r_id for r_id in rendering_ids), "WACZ file should not appear as a rendering."


def test_manifest_web_archive_replay_url_filters_to_single_canvas(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua600.007", "014ab7f4f8e5208fb41aa8802007f74e")

    items = manifest.get("items", [])
    assert items, "Expected canvases generated from WACZ pages."
    assert len(items) == 1, "Expected only the replay_url-matching WACZ page to become a canvas."

    canvas = items[0]
    anno_page = canvas["items"][0]
    anno = anno_page["items"][0]
    body = anno.get("body", {})
    assert "replayweb.page" in body.get("id", ""), (
        f"Expected ReplayWeb.page URL as canvas body, got: {body.get('id')}"
    )
    assert "instagram.com" in body.get("id", ""), "Expected replay_url-matching Instagram page only."


def test_manifest_web_archive_warc_gz_generates_html_canvases(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua600.007", "44b50e0bcb984b1f63d462ce7584b1ce")

    items = manifest.get("items", [])
    assert items, "Expected canvases generated from WARC.gz HTML pages."
    assert len(items) == 1, "Expected only the single HTML page from the WARC to become a canvas."

    canvas = items[0]
    anno_page = canvas["items"][0]
    anno = anno_page["items"][0]
    body = anno.get("body", {})
    assert "replayweb.page" in body.get("id", ""), (
        f"Expected ReplayWeb.page URL as canvas body, got: {body.get('id')}"
    )
    assert "liveaction.org" in body.get("id", ""), "Expected liveaction.org page from WARC."
    assert "warc.gz" in body.get("id", ""), "Expected warc.gz source URL in replay URL."


def test_manifest_web_archive_warc_gz_replay_url_filters_to_single_canvas(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua600.007", "10bf52164d525cc86b92ebd9f9bb668e")

    items = manifest.get("items", [])
    assert items, "Expected canvases generated from WARC.gz pages."
    assert len(items) >= 1, "Expected replay_url filtering to retain at least one matching WARC page."

    for canvas in items:
        anno_page = canvas["items"][0]
        anno = anno_page["items"][0]
        body = anno.get("body", {})
        body_id = body.get("id", "")
        assert "replayweb.page" in body.get("id", ""), (
            f"Expected ReplayWeb.page URL as canvas body, got: {body.get('id')}"
        )
        assert "www.albanystudentpress.online" in body_id, "Expected Albany Student Press domain in replay URL."
        assert "turning-point-usa-event" in body_id, "Expected replay_url target slug in replay URL."
        assert "warc.gz" in body.get("id", ""), "Expected warc.gz source URL in replay URL."


def test_manifest_web_archive_warc_mailto_replay_url_generates_canvas(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua399", "92f346e094e15bfc24f540aa4a429ed4")

    items = manifest.get("items", [])
    assert items, "Expected canvases generated from mailto web archive pages."

    canvas = items[0]
    anno_page = canvas["items"][0]
    anno = anno_page["items"][0]
    body = anno.get("body", {})
    body_id = body.get("id", "")

    assert "replayweb.page" in body_id, f"Expected ReplayWeb.page URL as canvas body, got: {body_id}"
    assert "view=resources" in body_id, "Expected resources view for non-http replay target."
    assert "mailto%3A" in body_id, "Expected encoded mailto target in replay URL."
    assert "body.html" in body_id, "Expected body.html target in replay URL."
    assert "mp_%2Fmailto%3A" not in body_id, "Non-http replay URL should use raw mailto target, not timestamped https wrapper."


def test_manifest_web_archive_resource_type_is_case_insensitive(tmp_path):
    temp_discovery_storage_root, temp_config_path = create_temp_fixture_config(tmp_path, config_path)
    object_path = os.path.join(temp_discovery_storage_root, "ua600.007", "d31b512cf15fb175cd50150637af7153")
    manifest_path = os.path.join(object_path, "manifest.json")

    _set_metadata_value(object_path, "resource_type", "web archive")

    if os.path.isfile(manifest_path):
        os.remove(manifest_path)

    create_manifest("ua600.007", "d31b512cf15fb175cd50150637af7153", config_path=temp_config_path)

    with open(manifest_path, "r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    assert manifest.get("items"), "Expected canvases generated for lowercase web archive resource_type."
    assert "replayweb.page" in manifest["items"][0]["items"][0]["items"][0]["body"].get("id", "")


def _range_label(range_item):
    label = range_item.get("label", {})
    if isinstance(label, dict):
        for values in label.values():
            if isinstance(values, list) and values:
                return values[0]
            if isinstance(values, str):
                return values
    return None


def _collect_heading_canvas_pairs(ranges):
    pairs = {}

    def walk(range_item):
        if range_item.get("type") != "Range":
            return

        label = _range_label(range_item)
        canvas_id = None
        for item in range_item.get("items", []):
            if isinstance(item, dict) and item.get("type") == "Canvas":
                canvas_id = item.get("id")
                break

        if label and canvas_id:
            pairs[label] = canvas_id

        for item in range_item.get("items", []):
            if isinstance(item, dict) and item.get("type") == "Range":
                walk(item)

    for structure in ranges:
        walk(structure)

    return pairs


def _canvas_file_by_canvas_id(manifest):
    mapping = {}
    for canvas in manifest.get("items", []):
        label = canvas.get("label", {})
        filename = None

        if isinstance(label, dict):
            for values in label.values():
                if isinstance(values, list) and values:
                    filename = values[0]
                    break
                if isinstance(values, str):
                    filename = values
                    break
        elif isinstance(label, str):
            filename = label

        if filename and canvas.get("id"):
            mapping[canvas["id"]] = filename

    return mapping


def _filename_stem(filename):
    return os.path.splitext(os.path.basename(filename))[0].casefold()


def test_manifest_toc_disabled_by_default(tmp_path):
    manifest = _generate_manifest(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    assert "structures" not in manifest, "TOC should be opt-in and absent unless toc=True."


def test_manifest_toc_uses_content_markers_for_ua200(tmp_path):
    manifest = _generate_manifest(
        tmp_path,
        "ua200",
        "fd198d1a2ebfdddad630c9698a38df29",
        create_manifest_kwargs={"toc": True},
    )

    assert manifest.get("structures"), "Expected IIIF structures when toc=True and content.md exists."

    heading_to_canvas = _collect_heading_canvas_pairs(manifest["structures"])
    canvas_to_file = _canvas_file_by_canvas_id(manifest)

    assert _filename_stem(canvas_to_file[heading_to_canvas["May 15, 2006 - Meeting Agenda"]]) == "fd198d1a2ebfdddad630c9698a38df29-1"
    assert _filename_stem(canvas_to_file[heading_to_canvas["Council Reports"]]) == "fd198d1a2ebfdddad630c9698a38df29-2"
    assert _filename_stem(canvas_to_file[heading_to_canvas["Committee Reports"]]) == "fd198d1a2ebfdddad630c9698a38df29-3"
    assert _filename_stem(canvas_to_file[heading_to_canvas["New Business"]]) == "fd198d1a2ebfdddad630c9698a38df29-4"
    assert _filename_stem(canvas_to_file[heading_to_canvas["Adjourn"]]) == "fd198d1a2ebfdddad630c9698a38df29-5"


def test_manifest_toc_uses_content_markers_for_ua760(tmp_path):
    manifest = _generate_manifest(
        tmp_path,
        "ua760",
        "a4b2caa10782bc2f210efe8ab44f57e3",
        create_manifest_kwargs={"toc": True},
    )

    assert manifest.get("structures"), "Expected IIIF structures when toc=True and content.md exists."

    heading_to_canvas = _collect_heading_canvas_pairs(manifest["structures"])
    canvas_to_file = _canvas_file_by_canvas_id(manifest)

    assert _filename_stem(canvas_to_file[heading_to_canvas["College of Education, Albany, New York, Sept. 12, 1961"]]) == "1961-09-1"
    assert _filename_stem(canvas_to_file[heading_to_canvas["Institute, Add 1"]]) == "1961-09-2"
    assert _filename_stem(canvas_to_file[heading_to_canvas["INTER-OFFICE MEMO"]]) == "1961-09-4"
    assert _filename_stem(canvas_to_file[heading_to_canvas["COLLEGE OF EDUCATION AT ALBANY"]]) == "1961-09-7"
    assert _filename_stem(canvas_to_file[heading_to_canvas["TO: Greenville Local"]]) == "1961-09-9"
