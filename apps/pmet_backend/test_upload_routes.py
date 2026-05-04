from __future__ import annotations

import gzip
import os
import shutil
import unittest

from fastapi.testclient import TestClient

from pmet_backend.api.main import app
from pmet_backend.config import config


class UploadRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.created_dirs: set[str] = set()

    def tearDown(self):
        self.client.close()
        for directory in self.created_dirs:
            shutil.rmtree(directory, ignore_errors=True)

    def _upload(self, filename: str, content: bytes, file_type: str, task_id: str | None = None):
        data = {"file_type": file_type}
        if task_id is not None:
            data["task_id"] = task_id
        response = self.client.post(
            "/api/files/upload",
            files={"file": (filename, content, "application/octet-stream")},
            data=data,
        )
        if response.status_code < 400:
            saved_path = config.PROJECT_ROOT / response.json()["path"]
            self.created_dirs.add(str(saved_path.parent))
        return response

    def _issue_session(self):
        response = self.client.post("/api/files/issue-session")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_accepts_gene_text_upload(self):
        response = self._upload("genes.txt", b"AT1G01010\nAT1G01020\n", "genes")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["path"].startswith("results/app/temp_"))
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
        # Without a task_id we still fall back to the temp dir layout.
        self.assertTrue(response.json()["path"].startswith("results/app/temp_"))
        self.assertTrue(response.json()["path"].endswith("/motifs.meme"))

    def test_accepts_plain_fasta_upload(self):
        response = self._upload("intervals.fa", b">peak1\nACGT\n", "fasta")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # No task_id supplied -> falls back to temp dir layout.
        self.assertTrue(payload["path"].startswith("results/app/temp_"))
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

    def test_upload_replaces_stale_symlink_without_following_it(self):
        session = "pmet_stale_link"
        upload_dir = config.RESULT_DIR / session / "upload"
        upload_dir.mkdir(parents=True, exist_ok=True)
        self.created_dirs.add(str(config.RESULT_DIR / session))
        target = config.RESULT_DIR / session / "target.txt"
        target.write_text("original\n")
        stale_link = upload_dir / "genes.txt"
        try:
            os.symlink(target, stale_link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unsupported: {exc}")

        response = self._upload("genes.txt", b"new upload\n", "genes", task_id=session)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(target.read_text(), "original\n")
        self.assertFalse(stale_link.is_symlink())
        self.assertEqual(stale_link.read_text(), "new upload\n")

    def test_session_id_groups_uploads_in_one_directory(self):
        session = "pmet_abc123"
        r1 = self._upload("genes.txt", b"AT1G01010\n", "genes", task_id=session)
        r2 = self._upload("genome.fa", b">c1\nACGT\n", "fasta", task_id=session)
        r3 = self._upload("motifs.meme", b"MEME version 4\n", "meme", task_id=session)

        for r in (r1, r2, r3):
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["path"].startswith(f"results/app/{session}/upload/"))

        # All three landed in the same directory.
        parents = {(config.PROJECT_ROOT / r.json()["path"]).parent for r in (r1, r2, r3)}
        self.assertEqual(len(parents), 1)

    def test_session_id_rejects_unsafe_value(self):
        response = self._upload("genes.txt", b"x\n", "genes", task_id="../etc/passwd")
        self.assertEqual(response.status_code, 400)

    def test_filename_is_sanitized(self):
        response = self._upload("../../weird name.txt", b"x\n", "genes")
        self.assertEqual(response.status_code, 200)
        # `..` and spaces are stripped/replaced; extension preserved.
        self.assertTrue(response.json()["path"].endswith("/weird_name.txt"))

    def test_rejects_wrong_extension_for_slot(self):
        response = self._upload("not_genes.csv", b"a,b\n1,2\n", "genes")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file extension for genes", response.json()["detail"])

    def test_rejects_unexpected_gzip_payload(self):
        gzipped_text = gzip.compress(b"not a fasta file\n")
        response = self._upload("bad_input.txt.gz", gzipped_text, "fasta")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file extension for fasta", response.json()["detail"])

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
