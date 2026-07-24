import os
import yaml

from iiiflow.manifest_builders.assembly import create_iiif_manifest as build_iiif_manifest
from iiiflow.manifest_builders.policies import (
    build_manifest_label,
    build_rights_and_attribution,
    resolve_resource_source,
    thumbnail_data,
)
from iiiflow.manifest_builders.renderings import append_manifest_renderings
from iiiflow.manifest_builders.services import attach_search_service_if_configured
from test_utils import create_temp_fixture_config


class DummyManifest:
    pass


def _load_metadata(object_path):
    metadata_path = os.path.join(object_path, "metadata.yml")
    with open(metadata_path, "r", encoding="utf-8") as metadata_file:
        return yaml.safe_load(metadata_file) or {}


def _prepare_fixture(tmp_path, collection_id, object_id):
    temp_discovery_storage_root, temp_config_path = create_temp_fixture_config(tmp_path)
    object_path = os.path.join(temp_discovery_storage_root, collection_id, object_id)
    metadata = _load_metadata(object_path)
    return object_path, metadata, temp_config_path


def test_build_manifest_label_uses_real_fixture_manifest_label(tmp_path):
    object_path, metadata, _ = _prepare_fixture(tmp_path, "apap401", "56b3ab1c00ac03862ef0f47650905013")

    label = build_manifest_label(metadata)

    assert label == "George Edwards, 2010 April 6"


def test_build_rights_and_attribution_normalizes_inc_edu_url_from_fixture(tmp_path):
    object_path, metadata, _ = _prepare_fixture(tmp_path, "apap401", "56b3ab1c00ac03862ef0f47650905013")

    rights, attribution = build_rights_and_attribution(metadata)

    assert rights == "https://rightsstatements.org/vocab/InC-EDU/1.0/"
    assert "InC-EDU.dark.svg" in attribution


def test_resolve_resource_source_prefers_ogg_for_audio_fixture(tmp_path):
    object_path, metadata, _ = _prepare_fixture(tmp_path, "apap401", "56b3ab1c00ac03862ef0f47650905013")

    files_path, resource_format = resolve_resource_source(object_path, metadata["resource_type"])

    assert resource_format == "ogg"
    assert files_path.endswith(os.path.join("56b3ab1c00ac03862ef0f47650905013", "ogg"))


def test_resolve_resource_source_falls_back_to_audio_for_video_fixture_without_webm(tmp_path):
    object_path, metadata, _ = _prepare_fixture(tmp_path, "apap304", "c68230abba081dec0c82522ffce1d285")

    files_path, resource_format = resolve_resource_source(object_path, metadata["resource_type"])

    assert resource_format in {"ogg", "mp3"}
    assert files_path.endswith(os.path.join("c68230abba081dec0c82522ffce1d285", resource_format))


def test_thumbnail_data_reads_real_fixture_dimensions(tmp_path):
    object_path, metadata, _ = _prepare_fixture(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    thumb = thumbnail_data(object_path, "https://media.archives.albany.edu/ua200/fd198d1a2ebfdddad630c9698a38df29")

    assert thumb["url"].endswith("/thumbnail.jpg")
    assert thumb["width"] == 300
    assert thumb["height"] == 225


def test_append_manifest_renderings_uses_content_txt_and_original_label_from_fixture(tmp_path):
    object_path, metadata, _ = _prepare_fixture(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    files_path, _ = resolve_resource_source(object_path, metadata["resource_type"])
    manifest = DummyManifest()

    append_manifest_renderings(
        manifest,
        files_path,
        "https://media.archives.albany.edu/ua200/fd198d1a2ebfdddad630c9698a38df29",
        metadata,
    )

    assert hasattr(manifest, "rendering")
    rendering_ids = [item.get("id", "") for item in manifest.rendering]
    assert any(item_id.endswith("/content.txt") for item_id in rendering_ids)
    assert all("/txt/" not in item_id for item_id in rendering_ids)

    labels = [item.get("label", "") for item in manifest.rendering]
    assert any("(Original)" in label for label in labels)


def test_attach_search_service_uses_real_hocr_fixture_and_config(tmp_path):
    object_path, metadata, temp_config_path = _prepare_fixture(tmp_path, "ua200", "fd198d1a2ebfdddad630c9698a38df29")

    files_path, _ = resolve_resource_source(object_path, metadata["resource_type"])
    manifest = DummyManifest()

    attach_search_service_if_configured(
        manifest,
        files_path,
        "https://media.archives.albany.edu",
        "https://media.archives.albany.edu/ua200/fd198d1a2ebfdddad630c9698a38df29",
        "en",
        temp_config_path,
    )

    assert hasattr(manifest, "service")
    assert manifest.service[0]["type"] == "SearchService"
    assert manifest.service[0]["id"] == "https://media.archives.albany.edu/search/1/ua200/fd198d1a2ebfdddad630c9698a38df29"


def test_create_iiif_manifest_treats_email_archive_as_web_archive(tmp_path, monkeypatch):
    file_dir = tmp_path / "warc.gz"
    file_dir.mkdir()
    (file_dir / "sample.warc.gz").write_bytes(b"not-an-image")

    calls = {"web_archive": False}

    def fake_create_web_archive_canvases(manifest, file_dir, obj_url_root, thumbnail_data, lang_code, metadata):
        calls["web_archive"] = True

    def fail_if_image_dimensions_are_requested(_path):
        raise AssertionError("get_image_dimensions should not be called for email/web archive resources")

    monkeypatch.setattr("iiiflow.manifest_builders.assembly.create_web_archive_canvases", fake_create_web_archive_canvases)
    monkeypatch.setattr("iiiflow.manifest_builders.assembly.get_image_dimensions", fail_if_image_dimensions_are_requested)
    monkeypatch.setattr("iiiflow.manifest_builders.assembly.append_manifest_renderings", lambda *args, **kwargs: None)
    monkeypatch.setattr("iiiflow.manifest_builders.assembly.attach_search_service_if_configured", lambda *args, **kwargs: None)

    manifest = build_iiif_manifest(
        str(file_dir),
        "https://media.archives.albany.edu",
        "https://media.archives.albany.edu/ua399/92f346e094e15bfc24f540aa4a429ed4",
        "https://iiif.archives.albany.edu/iiif/3/ua399/92f346e094e15bfc24f540aa4a429ed4",
        "warc.gz",
        "Web Archive",
        {
            "license": "Unknown",
            "rights_statement": "https://rightsstatements.org/vocab/InC-EDU/1.0/",
        },
        {"url": "https://media.archives.albany.edu/ua399/92f346e094e15bfc24f540aa4a429ed4/thumbnail.jpg", "width": None, "height": None},
        "email",
        "en",
        str(tmp_path / "config.yml"),
    )

    assert calls["web_archive"] is True
    assert manifest is not None
