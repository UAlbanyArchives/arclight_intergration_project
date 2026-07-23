import os
import yaml
from iiiflow import create_transcription
from test_utils import load_config, iterate_collections_and_objects, create_temp_fixture_config, assert_text_file_similar, assert_vtt_matches

config_path = "./.iiiflow.yml"
discovery_storage_root, log_file_path = load_config(config_path)

def test_transcription(tmp_path):
    """Test A/V transcriptions"""

    temp_discovery_storage_root, temp_config_path = create_temp_fixture_config(tmp_path, config_path)

    def test_action(collection_id, object_id, object_path):
        canonical_object_path = os.path.join(discovery_storage_root, collection_id, object_id)
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

                if not should_run_whisper:
                    assert not os.path.isfile(content_path), (
                        f"content.txt should not be created when automated_text_tool is '{automated_text_tool_normalized}'"
                    )
                    break

                assert os.path.isfile(content_path), f"Missing generated content file: {content_path}"
                assert_text_file_similar(content_path, canonical_content_path, min_length_ratio=0.7, min_similarity_ratio=0.4)

                for input_file in os.listdir(format_path):
                    if input_file.lower().endswith(av_format):
                        vtt_file = os.path.splitext(input_file)[0] + ".vtt"
                        txt_file = os.path.splitext(input_file)[0] + ".txt"
                        vtt_path = os.path.join(object_path, "vtt", vtt_file)
                        txt_path = os.path.join(object_path, "txt", txt_file)
                        canonical_vtt_path = os.path.join(canonical_object_path, "vtt", vtt_file)
                        canonical_txt_path = os.path.join(canonical_object_path, "txt", txt_file)

                        if os.path.isfile(canonical_vtt_path):
                            assert os.path.isfile(vtt_path), f"Missing generated VTT file: {vtt_path}"
                            assert_vtt_matches(vtt_path, canonical_vtt_path)
                        if os.path.isfile(canonical_txt_path):
                            assert os.path.isfile(txt_path), f"Missing generated TXT file: {txt_path}"
                            assert_text_file_similar(txt_path, canonical_txt_path, min_length_ratio=0.7, min_similarity_ratio=0.4)

                break

    iterate_collections_and_objects(temp_discovery_storage_root, test_action)
