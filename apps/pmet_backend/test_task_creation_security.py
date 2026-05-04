from __future__ import annotations

import shutil
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from pmet_backend.api.main import app
from pmet_backend.api import upload_sessions as _sessions
from pmet_backend.config import config


class TaskCreationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.task_ids: set[str] = set()
        # Reset session/rate-limit state so cross-suite ordering doesn't
        # tip the per-IP issue-session rate limit.
        _sessions._SESSIONS.clear()
        _sessions._RATE_BUCKETS.clear()

    def tearDown(self):
        self.client.close()
        for task_id in self.task_ids:
            shutil.rmtree(config.RESULT_DIR / task_id, ignore_errors=True)
            (config.TASKS_DIR / f"{task_id}.json").unlink(missing_ok=True)

    def _issue_session(self) -> dict:
        response = self.client.post("/api/files/issue-session")
        self.assertEqual(response.status_code, 200)
        session = response.json()
        self.task_ids.add(session["session_id"])
        return session

    def _upload(self, session: dict, filename: str, body: bytes, file_type: str) -> str:
        response = self.client.post(
            "/api/files/upload",
            files={"file": (filename, body, "application/octet-stream")},
            data={"task_id": session["session_id"], "file_type": file_type},
            headers={"X-PMET-Session-Token": session["session_token"]},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["path"]

    def _use_example(self, session: dict, mode: str, slot: str) -> str:
        response = self.client.post(
            "/api/files/use-example",
            data={
                "task_id": session["session_id"],
                "mode": mode,
                "slot": slot,
                "session_token": session["session_token"],
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["path"]

    def _payload(self, session: dict, **overrides) -> dict:
        payload = {
            "email": "security@example.com",
            "mode": "intervals",
            "task_id": session["session_id"],
            "session_token": session["session_token"],
            "genes_file": overrides.pop("genes_file"),
            "fasta_file": overrides.pop("fasta_file"),
            "meme_file": overrides.pop("meme_file"),
        }
        payload.update(overrides)
        return payload

    def test_create_task_binds_session_and_drops_token_from_metadata(self):
        session = self._issue_session()
        genes = self._upload(session, "genes.txt", b"peak1\n", "genes")
        fasta = self._use_example(session, "intervals", "fasta")
        meme = self._use_example(session, "intervals", "meme")

        with patch("celery.app.task.Task.delay") as delay:
            response = self.client.post(
                "/api/tasks",
                json=self._payload(session, genes_file=genes, fasta_file=fasta, meme_file=meme),
            )

        self.assertEqual(response.status_code, 200, response.text)
        delay.assert_called_once()
        meta = (config.TASKS_DIR / f"{session['session_id']}.json").read_text()
        self.assertNotIn("session_token", meta)
        self.assertIn('"fasta_file": "data/demos/intervals/indexing/intervals.fa"', meta)

    def test_create_task_rejects_bad_session_token_before_path_checks(self):
        session = self._issue_session()
        payload = self._payload(
            {**session, "session_token": "wrong-token"},
            genes_file="../../etc/passwd",
            fasta_file="../../etc/passwd",
            meme_file="../../etc/passwd",
        )

        with patch("celery.app.task.Task.delay") as delay:
            response = self.client.post("/api/tasks", json=payload)

        self.assertEqual(response.status_code, 401)
        delay.assert_not_called()

    def test_create_task_rejects_cross_session_upload_path(self):
        owner = self._issue_session()
        attacker = self._issue_session()
        stolen_genes = self._upload(owner, "genes.txt", b"peak1\n", "genes")
        fasta = self._use_example(attacker, "intervals", "fasta")
        meme = self._use_example(attacker, "intervals", "meme")

        with patch("celery.app.task.Task.delay") as delay:
            response = self.client.post(
                "/api/tasks",
                json=self._payload(attacker, genes_file=stolen_genes, fasta_file=fasta, meme_file=meme),
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("genes_file must be under this session", response.json()["detail"])
        delay.assert_not_called()

    def test_create_task_rejects_wrong_slot_demo_path(self):
        session = self._issue_session()
        fasta = self._use_example(session, "intervals", "fasta")
        meme = self._use_example(session, "intervals", "meme")

        with patch("celery.app.task.Task.delay") as delay:
            response = self.client.post(
                "/api/tasks",
                json=self._payload(session, genes_file=fasta, fasta_file=fasta, meme_file=meme),
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("genes_file must be under this session", response.json()["detail"])
        delay.assert_not_called()

    def test_create_task_rejects_duplicate_task_id(self):
        session = self._issue_session()
        config.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        (config.TASKS_DIR / f"{session['session_id']}.json").write_text("{}")

        with patch("celery.app.task.Task.delay") as delay:
            response = self.client.post(
                "/api/tasks",
                json=self._payload(
                    session,
                    genes_file="results/nope/upload/genes.txt",
                    fasta_file="results/nope/upload/fasta.fa",
                    meme_file="results/nope/upload/motif.meme",
                ),
            )

        self.assertEqual(response.status_code, 409)
        delay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
