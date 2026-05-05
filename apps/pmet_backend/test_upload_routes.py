from __future__ import annotations

import gzip
import os
import shutil
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from pmet_backend.api.main import app
from pmet_backend.api import upload_sessions as _sessions
from pmet_backend.config import config


class UploadRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.created_dirs: set[str] = set()
        # Reset session state between tests for isolation. Rate
        # limiting now lives in nginx, not in the app, so there's no
        # in-process bucket to clear; TestClient bypasses nginx so the
        # tests don't trip the 10/min cap regardless.
        _sessions._SESSIONS.clear()

    def tearDown(self):
        self.client.close()
        for directory in self.created_dirs:
            shutil.rmtree(directory, ignore_errors=True)

    def _issue_session(self):
        response = self.client.post("/api/files/issue-session")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _upload(
        self,
        filename: str,
        content: bytes,
        file_type: str,
        session_id: str | None = None,
        session_token: str | None = None,
    ):
        """Upload helper. If session_id is None, a fresh session is issued and
        used; tests that want to drive the negative-auth paths can set
        session_id explicitly and override session_token (or pass an empty
        string to omit the header)."""
        if session_id is None:
            session = self._issue_session()
            session_id = session["session_id"]
            if session_token is None:
                session_token = session["session_token"]
        data = {"file_type": file_type}
        headers = {"X-PMET-Session-Id": session_id}
        if session_token:
            headers["X-PMET-Session-Token"] = session_token
        response = self.client.post(
            "/api/files/upload",
            files={"file": (filename, content, "application/octet-stream")},
            data=data,
            headers=headers,
        )
        if response.status_code < 400:
            saved_path = config.PROJECT_ROOT / response.json()["path"]
            self.created_dirs.add(str(saved_path.parent))
        return response

    # ---------- happy paths ----------

    def test_accepts_gene_text_upload(self):
        response = self._upload("genes.txt", b"AT1G01010\nAT1G01020\n", "genes")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["path"].endswith("/genes.txt"))
        saved_path = config.PROJECT_ROOT / payload["path"]
        self.assertEqual(saved_path.read_text(), "AT1G01010\nAT1G01020\n")

    def test_accepts_gene_tsv_upload(self):
        response = self._upload("genes.tsv", b"cluster\tgene\n1\tAT1G01010\n", "genes")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["path"].endswith("/genes.tsv"))

    def test_accepts_meme_upload(self):
        response = self._upload("motifs.meme", b"MEME version 4\n", "meme")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["path"].endswith("/motifs.meme"))

    def test_accepts_plain_fasta_upload(self):
        response = self._upload("intervals.fa", b">peak1\nACGT\n", "fasta")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["path"].endswith("/intervals.fa"))
        saved_path = config.PROJECT_ROOT / payload["path"]
        self.assertEqual(saved_path.read_text(), ">peak1\nACGT\n")

    def test_decompresses_gzipped_fasta_upload(self):
        gzipped_fasta = gzip.compress(b">chr1\nACGTACGT\n")
        response = self._upload("genome.fasta.gz", gzipped_fasta, "fasta")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["path"].endswith("/genome.fasta"))
        saved_path = config.PROJECT_ROOT / payload["path"]
        self.assertEqual(saved_path.read_text(), ">chr1\nACGTACGT\n")

    def test_decompresses_gzipped_gff3_upload(self):
        gzipped_gff3 = gzip.compress(b"##gff-version 3\nchr1\tsrc\tgene\t1\t10\t.\t+\t.\tID=g1\n")
        response = self._upload("annotation.gff3.gz", gzipped_gff3, "gff3")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["path"].endswith("/annotation.gff3"))
        saved_path = config.PROJECT_ROOT / payload["path"]
        self.assertIn("##gff-version 3", saved_path.read_text())

    def test_session_id_groups_uploads_in_one_directory(self):
        session = self._issue_session()
        sid = session["session_id"]
        token = session["session_token"]
        r1 = self._upload("genes.txt", b"AT1G01010\n", "genes", session_id=sid, session_token=token)
        r2 = self._upload("genome.fa", b">c1\nACGT\n", "fasta", session_id=sid, session_token=token)
        r3 = self._upload("motifs.meme", b"MEME version 4\n", "meme", session_id=sid, session_token=token)

        for r in (r1, r2, r3):
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["path"].endswith("/upload/" + r.json()["path"].split("/")[-1]))

        parents = {(config.PROJECT_ROOT / r.json()["path"]).parent for r in (r1, r2, r3)}
        self.assertEqual(len(parents), 1)

    def test_filename_is_sanitized(self):
        response = self._upload("../../weird name.txt", b"x\n", "genes")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["path"].endswith("/weird_name.txt"))

    # ---------- write-through guard (#15) ----------

    def test_upload_replaces_stale_symlink_without_following_it(self):
        session = self._issue_session()
        sid = session["session_id"]
        upload_dir = config.RESULT_DIR / sid / "upload"
        upload_dir.mkdir(parents=True, exist_ok=True)
        self.created_dirs.add(str(config.RESULT_DIR / sid))
        target = config.RESULT_DIR / sid / "target.txt"
        target.write_text("original\n")
        stale_link = upload_dir / "genes.txt"
        try:
            os.symlink(target, stale_link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unsupported: {exc}")

        response = self._upload("genes.txt", b"new upload\n", "genes", session_id=sid, session_token=session["session_token"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(target.read_text(), "original\n")
        self.assertFalse(stale_link.is_symlink())
        self.assertEqual(stale_link.read_text(), "new upload\n")

    # ---------- /upload session-token gate (#17) ----------

    def test_upload_requires_session_token_header(self):
        session = self._issue_session()
        sid = session["session_id"]

        # Session id but no token → 401.
        no_header = self._upload(
            "genes.txt", b"x\n", "genes", session_id=sid, session_token=""
        )
        self.assertEqual(no_header.status_code, 401)

        # Wrong token → 401.
        wrong = self._upload(
            "genes.txt", b"x\n", "genes", session_id=sid, session_token="not-the-token"
        )
        self.assertEqual(wrong.status_code, 401)

        # Cross-session token (issued for sid_b) → 401 against sid_a.
        sid_b = self._issue_session()
        cross = self._upload(
            "genes.txt", b"x\n", "genes", session_id=sid, session_token=sid_b["session_token"]
        )
        self.assertEqual(cross.status_code, 401)

        # Correct token → 200.
        ok = self._upload(
            "genes.txt", b"x\n", "genes", session_id=sid, session_token=session["session_token"]
        )
        self.assertEqual(ok.status_code, 200)

    def test_upload_requires_session_id_header(self):
        session = self._issue_session()
        with patch(
            "pmet_backend.api.routes.files._parse_upload_form",
            side_effect=AssertionError("body was parsed before session-id validation"),
        ):
            response = self.client.post(
                "/api/files/upload",
                files={"file": ("genes.txt", b"x\n", "application/octet-stream")},
                data={"file_type": "genes"},
                headers={"X-PMET-Session-Token": session["session_token"]},
            )
        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_missing_token_before_form_parse(self):
        session = self._issue_session()
        with patch(
            "pmet_backend.api.routes.files._parse_upload_form",
            side_effect=AssertionError("body was parsed before token validation"),
        ):
            response = self.client.post(
                "/api/files/upload",
                files={"file": ("genes.txt", b"x\n", "application/octet-stream")},
                data={"file_type": "genes"},
                headers={"X-PMET-Session-Id": session["session_id"]},
            )
        self.assertEqual(response.status_code, 401)

    def test_session_id_rejects_unsafe_value(self):
        response = self._upload(
            "genes.txt", b"x\n", "genes",
            session_id="../etc/passwd",
            session_token="anything",
        )
        self.assertEqual(response.status_code, 400)

    # ---------- size + bomb caps (#17) ----------

    def test_upload_rejects_oversize_raw(self):
        with patch.dict(
            "pmet_backend.api.routes.files._RAW_MAX_BYTES_BY_TYPE",
            {"fasta": 1024},
        ):
            response = self._upload("huge.fa", b"\0" * 2048, "fasta")
        self.assertEqual(response.status_code, 413)
        self.assertIn("size cap", response.json()["detail"].lower())

    def test_upload_rejects_oversize_gzip_raw(self):
        payload = bytes(i % 251 for i in range(2048))
        gzipped = gzip.compress(payload, compresslevel=0)
        self.assertGreater(len(gzipped), 1024)

        with patch.dict(
            "pmet_backend.api.routes.files._RAW_MAX_BYTES_BY_TYPE",
            {"fasta": 1024},
        ):
            response = self._upload("huge.fasta.gz", gzipped, "fasta")

        self.assertEqual(response.status_code, 413)
        self.assertIn("size cap", response.json()["detail"].lower())

    def test_upload_rejects_gzip_bomb(self):
        bomb = gzip.compress(b"\0" * 2048, compresslevel=9)
        with patch("pmet_backend.api.routes.files._GENOME_DECOMPRESSED_MAX_BYTES", 1024):
            response = self._upload("bomb.fasta.gz", bomb, "fasta")
        self.assertEqual(response.status_code, 413)
        self.assertIn("decompressed-size", response.json()["detail"].lower())

    def test_upload_rejects_oversize_genes_small_cap(self):
        # genes / meme have a much tighter 2 MB raw cap than fasta / gff3,
        # because cluster→gene tab files are inherently small. Verify
        # that the per-type lookup is wired up by patching just the genes
        # entry and confirming a fasta upload of the same size still
        # passes (uses its own 1 GB cap).
        with patch.dict(
            "pmet_backend.api.routes.files._RAW_MAX_BYTES_BY_TYPE",
            {"genes": 16},
        ):
            small_gene = self._upload("g.txt", b"a\nb\nc\n", "genes")
            self.assertEqual(small_gene.status_code, 200)
            big_gene = self._upload("g.txt", b"x" * 64, "genes")
        self.assertEqual(big_gene.status_code, 413)
        self.assertIn("size cap", big_gene.json()["detail"].lower())

    def test_upload_rejects_oversize_meme_small_cap(self):
        with patch.dict(
            "pmet_backend.api.routes.files._RAW_MAX_BYTES_BY_TYPE",
            {"meme": 16},
        ):
            response = self._upload("m.meme", b"x" * 64, "meme")
        self.assertEqual(response.status_code, 413)
        self.assertIn("size cap", response.json()["detail"].lower())

    def test_upload_rejects_session_file_quota(self):
        session = self._issue_session()
        with patch("pmet_backend.api.upload_sessions.SESSION_UPLOAD_MAX_FILES", 1):
            first = self._upload(
                "genes.txt", b"x\n", "genes",
                session_id=session["session_id"],
                session_token=session["session_token"],
            )
            second = self._upload(
                "genes2.txt", b"y\n", "genes",
                session_id=session["session_id"],
                session_token=session["session_token"],
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 413)
        self.assertIn("quota", second.json()["detail"].lower())

    def test_upload_rejects_session_byte_quota_and_unlinks_file(self):
        session = self._issue_session()
        with patch("pmet_backend.api.upload_sessions.SESSION_UPLOAD_MAX_BYTES", 4):
            response = self._upload(
                "genes.txt", b"12345", "genes",
                session_id=session["session_id"],
                session_token=session["session_token"],
            )

        self.assertEqual(response.status_code, 413)
        upload_dir = config.RESULT_DIR / session["session_id"] / "upload"
        self.assertFalse((upload_dir / "genes.txt").exists())

    # ---------- format gating ----------

    def test_rejects_wrong_extension_for_slot(self):
        response = self._upload("not_genes.csv", b"a,b\n1,2\n", "genes")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file extension for genes", response.json()["detail"])

    def test_rejects_unexpected_gzip_payload(self):
        gzipped_text = gzip.compress(b"not a fasta file\n")
        response = self._upload("bad_input.txt.gz", gzipped_text, "fasta")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file extension for fasta", response.json()["detail"])

    # ---------- DELETE token gate (#14) ----------

    def test_delete_upload_requires_session_token_header(self):
        session = self._issue_session()
        upload = self._upload(
            "genes.txt", b"AT1G01010\n", "genes",
            session_id=session["session_id"],
            session_token=session["session_token"],
        )
        path = upload.json()["path"]

        no_header = self.client.delete("/api/files/upload", params={"path": path})
        self.assertEqual(no_header.status_code, 401)

        query_token = self.client.delete(
            "/api/files/upload",
            params={"path": path, "session_token": session["session_token"]},
        )
        self.assertEqual(query_token.status_code, 401)

        with_header = self.client.delete(
            "/api/files/upload",
            params={"path": path},
            headers={"X-PMET-Session-Token": session["session_token"]},
        )
        self.assertEqual(with_header.status_code, 200)
        self.assertFalse((config.PROJECT_ROOT / path).exists())

    # ---------- /use-example (#15) ----------

    def test_use_example_requires_session_token(self):
        session = self._issue_session()
        response = self.client.post(
            "/api/files/use-example",
            data={
                "task_id": session["session_id"],
                "mode": "intervals",
                "slot": "meme",
                "session_token": "wrong-token",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_use_example_returns_data_path_without_upload_symlink(self):
        session = self._issue_session()
        response = self.client.post(
            "/api/files/use-example",
            data={
                "task_id": session["session_id"],
                "mode": "intervals",
                "slot": "meme",
                "session_token": session["session_token"],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filename"], "motif.meme")
        self.assertEqual(payload["path"], "data/demos/intervals/indexing/motif.meme")
        self.assertTrue((config.PROJECT_ROOT / payload["path"]).is_file())
        self.assertFalse(
            (config.RESULT_DIR / session["session_id"] / "upload" / payload["filename"]).exists()
        )


if __name__ == "__main__":
    unittest.main()
