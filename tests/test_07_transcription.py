import os
import shutil
import yaml
from iiiflow import create_transcription
from test_utils import load_config, iterate_collections_and_objects, create_temp_fixture_config, assert_text_file_similar, assert_vtt_matches

config_path = "./.iiiflow.yml"
discovery_storage_root, log_file_path = load_config(config_path)

def test_transcription(tmp_path):
    """Test A/V transcriptions.

    Set IIIFLOW_TRANSCRIPTION_DEBUG_DIR to persist generated and canonical
    text artifacts outside pytest tmp directories for manual inspection.
    """

    temp_discovery_storage_root, temp_config_path = create_temp_fixture_config(tmp_path, config_path)

    def test_action(collection_id, object_id, object_path):
        canonical_object_path = os.path.join(discovery_storage_root, collection_id, object_id)
        debug_root = os.environ.get("IIIFLOW_TRANSCRIPTION_DEBUG_DIR")
        debug_object_path = None
        if debug_root:
            debug_object_path = os.path.join(debug_root, collection_id, object_id)
            os.makedirs(debug_object_path, exist_ok=True)

        def copy_debug_artifact(source_path, relative_path, bucket):
            if not debug_object_path or not os.path.isfile(source_path):
                return

            destination_path = os.path.join(debug_object_path, bucket, relative_path)
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            shutil.copy2(source_path, destination_path)

        def raise_with_debug_hint(error):
            if not debug_object_path:
                raise error
            raise AssertionError(f"{error}\nDebug artifacts: {debug_object_path}") from error

        metadata_path = os.path.join(object_path, "metadata.yml")
        metadata = {}
        if os.path.isfile(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as metadata_file:
                metadata = yaml.safe_load(metadata_file) or {}

        automated_text_tool = metadata.get("automated_text_tool")
        automated_text_tool_normalized = str(automated_text_tool).strip().lower() if automated_text_tool is not None else ""
        should_run_whisper = automated_text_tool is None or automated_text_tool_normalized == "whisper"

        formats = ["webm", "ogg", "mp3"]
        for av_format in formats:
            format_path = os.path.join(object_path, av_format)
            if os.path.isdir(format_path):
                content_path = os.path.join(object_path, "content.txt")
                canonical_content_path = os.path.join(canonical_object_path, "content.txt")
                if os.path.isfile(content_path):
                    os.remove(content_path)

                vtt_dir = os.path.join(object_path, "vtt")
                txt_dir = os.path.join(object_path, "txt")
                if os.path.isdir(vtt_dir):
                    for filename in os.listdir(vtt_dir):
                        os.remove(os.path.join(vtt_dir, filename))
                if os.path.isdir(txt_dir):
                    for filename in os.listdir(txt_dir):
                        os.remove(os.path.join(txt_dir, filename))

                create_transcription(collection_id, object_id, config_path=temp_config_path)

                copy_debug_artifact(content_path, "content.txt", "generated")
                copy_debug_artifact(canonical_content_path, "content.txt", "canonical")

                if not should_run_whisper:
                    assert not os.path.isfile(content_path), (
                        f"content.txt should not be created when automated_text_tool is '{automated_text_tool_normalized}'"
                    )
                    break

                assert os.path.isfile(content_path), f"Missing generated content file: {content_path}"
                try:
                    assert_text_file_similar(content_path, canonical_content_path, min_length_ratio=0.7, min_similarity_ratio=0.4)
                except AssertionError as error:
                    raise_with_debug_hint(error)

                for input_file in os.listdir(format_path):
                    if input_file.lower().endswith(av_format):
                        vtt_file = os.path.splitext(input_file)[0] + ".vtt"
                        txt_file = os.path.splitext(input_file)[0] + ".txt"
                        vtt_path = os.path.join(object_path, "vtt", vtt_file)
                        txt_path = os.path.join(object_path, "txt", txt_file)
                        canonical_vtt_path = os.path.join(canonical_object_path, "vtt", vtt_file)
                        canonical_txt_path = os.path.join(canonical_object_path, "txt", txt_file)

                        copy_debug_artifact(vtt_path, os.path.join("vtt", vtt_file), "generated")
                        copy_debug_artifact(txt_path, os.path.join("txt", txt_file), "generated")
                        copy_debug_artifact(canonical_vtt_path, os.path.join("vtt", vtt_file), "canonical")
                        copy_debug_artifact(canonical_txt_path, os.path.join("txt", txt_file), "canonical")

                        if os.path.isfile(canonical_vtt_path):
                            assert os.path.isfile(vtt_path), f"Missing generated VTT file: {vtt_path}"
                            try:
                                assert_vtt_matches(vtt_path, canonical_vtt_path)
                            except AssertionError as error:
                                raise_with_debug_hint(error)
                        if os.path.isfile(canonical_txt_path):
                            assert os.path.isfile(txt_path), f"Missing generated TXT file: {txt_path}"
                            try:
                                assert_text_file_similar(txt_path, canonical_txt_path, min_length_ratio=0.7, min_similarity_ratio=0.4)
                            except AssertionError as error:
                                raise_with_debug_hint(error)

                break

    iterate_collections_and_objects(temp_discovery_storage_root, test_action)
