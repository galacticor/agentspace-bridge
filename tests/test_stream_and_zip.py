"""Unit tests for build_advisor_skill_zip.py and _post_widget_rpc streaming."""

from __future__ import annotations

import io
import json
import pathlib
import tempfile
import unittest
import zipfile
from unittest import mock

import agentspace_cli
import build_advisor_skill_zip


class _FakeStreamResponse:
    """Minimal chunked response simulating split UTF-8 and JSON array frames."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def read1(self, _n: int = 16384) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def read(self, n: int = 16384) -> bytes:
        return self.read1(n)

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class TestBuildAdvisorSkillZip(unittest.TestCase):
    def test_valid_zip_layout_and_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            skill_dir = root / "skill"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "scripts").mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: test\ndescription: test\n---\nSee references/guide.md and scripts/check.py\n",
                encoding="utf-8",
            )
            (skill_dir / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (skill_dir / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")

            zip_a = root / "a.zip"
            zip_b = root / "b.zip"
            build_advisor_skill_zip.build_zip(skill_dir, zip_a)
            build_advisor_skill_zip.build_zip(skill_dir, zip_b)

            with zipfile.ZipFile(zip_a, "r") as zfa, zipfile.ZipFile(zip_b, "r") as zfb:
                self.assertIsNone(zfa.testzip())
                self.assertEqual(zfa.namelist(), zfb.namelist())
                self.assertIn("SKILL.md", zfa.namelist())
                self.assertIn("references/guide.md", zfa.namelist())
                self.assertIn("scripts/check.py", zfa.namelist())

    def test_missing_skill_md_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            empty_dir = root / "empty"
            empty_dir.mkdir()
            out_zip = root / "out.zip"
            with self.assertRaises(FileNotFoundError):
                build_advisor_skill_zip.build_zip(empty_dir, out_zip)
            self.assertFalse(out_zip.exists())


class TestPostWidgetRpcStream(unittest.TestCase):
    def test_split_utf8_and_json_array_frames(self) -> None:
        frame1 = json.dumps(
            {"answer": {"replies": [{"groundedContent": {"content": {"text": "Hello 🚀"}}}]}},
            ensure_ascii=False,
        )
        frame2 = json.dumps({"answer": {"state": "SUCCEEDED", "replies": []}})
        raw = f"[{frame1},{frame2}]".encode("utf-8")
        # Split right through the 4-byte emoji UTF-8 sequence
        split_idx = raw.index("🚀".encode("utf-8")) + 2
        chunks = [raw[:split_idx], raw[split_idx:]]

        fake_xsrf = {"xsrfToken": "tok", "csesidx": "12345"}
        with (
            mock.patch.object(agentspace_cli, "load_xsrf", return_value=(fake_xsrf, "fake.json")),
            mock.patch.object(agentspace_cli, "make_jwt", return_value="jwt"),
            mock.patch("urllib.request.urlopen", return_value=_FakeStreamResponse(chunks)),
        ):
            result, xsrf_path = agentspace_cli._post_widget_rpc(
                "widgetStreamAssist",
                {"query": {"text": "hi"}},
                csesidx="12345",
                timeout=30,
            )

        self.assertEqual(xsrf_path, "fake.json")
        self.assertEqual(len(result), 2)
        self.assertEqual(
            result[0]["answer"]["replies"][0]["groundedContent"]["content"]["text"],
            "Hello 🚀",
        )
        self.assertEqual(result[1]["answer"]["state"], "SUCCEEDED")


class TestAdaptiveContextRouter(unittest.TestCase):
    def test_upload_context_bundle_success_and_token_gate(self) -> None:
        with mock.patch.object(
            agentspace_cli,
            "_post_widget_rpc",
            return_value=({"addContextFileResponse": {"fileId": "fid-123", "tokenCount": 42000}}, "x.json"),
        ) as rpc_mock:
            fid, tok = agentspace_cli._upload_context_bundle(
                "collections/default_collection/engines/e/sessions/s1",
                b"hello world",
                "a" * 64,
                csesidx="12345",
            )
        self.assertEqual(fid, "fid-123")
        self.assertEqual(tok, 42000)
        endpoint, payload = rpc_mock.call_args[0][0], rpc_mock.call_args[0][1]
        self.assertEqual(endpoint, "widgetAddContextFile")
        self.assertEqual(payload["additionalParams"], {"token": "-", "origin": "ORIGIN_UNSPECIFIED"})
        self.assertEqual(payload["addContextFileRequest"]["mimeType"], "text/plain")

        with mock.patch.object(
            agentspace_cli,
            "_post_widget_rpc",
            return_value=({"addContextFileResponse": {"fileId": "fid-big", "tokenCount": 600_000}}, "x.json"),
        ):
            with self.assertRaises(ValueError):
                agentspace_cli._upload_context_bundle("sess", b"x", "b" * 64)

    def test_session_context_file_id_cache_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(agentspace_cli, "OUTPUTS_DIR", tmp):
                sess = "collections/default_collection/engines/e/sessions/sess999"
                agentspace_cli.update_session_context_file_id("tag1", sess, "hashA", "fid-A")
                self.assertEqual(
                    agentspace_cli.get_session_context_file_id("tag1", sess, "hashA"),
                    "fid-A",
                )
                agentspace_cli.clear_reusable_session("tag1", "model:gemini-4-argon", deleted_session_id=sess)
                self.assertIsNone(agentspace_cli.get_session_context_file_id("tag1", sess, "hashA"))

    def test_two_tier_router_inline_vs_file_upload_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            small_file = root / "small.txt"
            small_file.write_text("small content\n", encoding="utf-8")
            large_file = root / "large.txt"
            large_file.write_text("X" * (agentspace_cli.CONTEXT_INLINE_MAX_BYTES + 1024), encoding="utf-8")

            stream_calls: list[dict] = []
            upload_calls: list[dict] = []

            def fake_rpc(endpoint: str, payload: dict, **_kwargs: object) -> tuple[object, str]:
                if endpoint == "widgetAddContextFile":
                    upload_calls.append(payload)
                    return ({"addContextFileResponse": {"fileId": "fid-large-1", "tokenCount": 30000}}, "x.json")
                if endpoint == "widgetStreamAssist":
                    stream_calls.append(payload)
                    return (
                        [
                            {
                                "streamAssistResponse": {
                                    "sessionInfo": {"session": "collections/default_collection/engines/e/sessions/s1"},
                                    "answer": {
                                        "state": "SUCCEEDED",
                                        "replies": [{"groundedContent": {"content": {"text": "ok"}}}],
                                    },
                                }
                            }
                        ],
                        "x.json",
                    )
                if endpoint in ("widgetGetSession", "widgetUpdateSession"):
                    return ({"session": {"displayName": "[agy-bridge] test"}}, "x.json")
                raise AssertionError(f"Unexpected endpoint: {endpoint}")

            with (
                mock.patch.object(agentspace_cli, "OUTPUTS_DIR", tmp),
                mock.patch.object(agentspace_cli, "_post_widget_rpc", side_effect=fake_rpc),
            ):
                # Tier 1: <= 96,000 bytes -> inline in query.parts[0].text, no upload, no fileIds
                agentspace_cli.ask_agentspace(
                    "inspect small",
                    input_files=[str(small_file)],
                    session_tag="t1",
                    cwd=tmp,
                )
                self.assertEqual(len(upload_calls), 0)
                req1 = stream_calls[-1]["streamAssistRequest"]
                self.assertNotIn("fileIds", req1)
                self.assertIn("small content", req1["query"]["parts"][0]["text"])

                # Tier 2: > 96,000 bytes -> widgetAddContextFile + fileIds
                agentspace_cli.ask_agentspace(
                    "inspect large",
                    input_files=[str(large_file)],
                    session_tag="t2",
                    cwd=tmp,
                )
                self.assertEqual(len(upload_calls), 1)
                req2 = stream_calls[-1]["streamAssistRequest"]
                self.assertEqual(req2.get("fileIds"), ["fid-large-1"])
                self.assertNotIn("XXXX", req2["query"]["parts"][0]["text"])

                # Tier 2 Turn 2: same > 96,000 byte file in same session -> cache hit, no re-upload
                agentspace_cli.ask_agentspace(
                    "follow up large",
                    input_files=[str(large_file)],
                    session_tag="t2",
                    cwd=tmp,
                )
                self.assertEqual(len(upload_calls), 1)
                req3 = stream_calls[-1]["streamAssistRequest"]
                self.assertEqual(req3.get("fileIds"), ["fid-large-1"])
                self.assertNotIn("XXXX", req3["query"]["parts"][0]["text"])


class TestExpandInputPaths(unittest.TestCase):
    def test_tilde_env_and_cwd_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            target = root / "sub" / "hello.py"
            target.parent.mkdir(parents=True)
            target.write_text("print('hi')\n", encoding="utf-8")

            with mock.patch.dict("os.environ", {"HOME": str(root), "MY_SUB": "sub"}):
                files_tilde, _ = agentspace_cli._expand_input_paths_with_report(["~/sub/hello.py"])
                self.assertEqual(len(files_tilde), 1)
                self.assertEqual(pathlib.Path(files_tilde[0][0]).resolve(), target.resolve())

                files_env, _ = agentspace_cli._expand_input_paths_with_report(["$MY_SUB/hello.py"], cwd="~")
                self.assertEqual(len(files_env), 1)
                self.assertEqual(pathlib.Path(files_env[0][0]).resolve(), target.resolve())

    def test_comma_separated_and_literal_comma_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            f1 = root / "a.py"
            f2 = root / "b.py"
            literal_comma = root / "report,final.txt"
            f1.write_text("a = 1\n", encoding="utf-8")
            f2.write_text("b = 2\n", encoding="utf-8")
            literal_comma.write_text("ok\n", encoding="utf-8")

            files_split, _ = agentspace_cli._expand_input_paths_with_report(["a.py, b.py"], cwd=tmp)
            self.assertEqual([d for _, d in files_split], ["a.py", "b.py"])

            files_lit, _ = agentspace_cli._expand_input_paths_with_report(["report,final.txt"], cwd=tmp)
            self.assertEqual([d for _, d in files_lit], ["report,final.txt"])

            with self.assertRaises(FileNotFoundError):
                agentspace_cli._expand_input_paths_with_report(["missing.py"], cwd=tmp)


if __name__ == "__main__":
    unittest.main()
