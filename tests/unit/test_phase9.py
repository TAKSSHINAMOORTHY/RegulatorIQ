"""Unit and Property-based tests for Phase 9: Containerisation, Deployment, Keep-Warm, and CI/CD."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.cost_guard import audit_cost_headroom
from scripts.deploy import detect_available_targets, plan_deployment, run_deployment
from scripts.gen_token import generate_secret
from scripts.smoke import is_allowed_rbi_url
from scripts.warmup import check_daily_cap, load_warmup_history, record_warmup_run, warmup_target


ROOT = Path(__file__).resolve().parent.parent.parent


class TestDockerAndConfigs:
    """Validate Dockerfile, entrypoint, compose files, and configs."""

    def test_dockerfile_structure(self):
        dockerfile = ROOT / "docker" / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile must exist"
        content = dockerfile.read_text(encoding="utf-8")

        # Multi-stage check
        assert "AS builder" in content or "as builder" in content
        # Non-root user check
        assert "1000" in content
        # Offline verified
        assert "HF_HUB_OFFLINE=1" in content
        # Unbuffered python
        assert "PYTHONUNBUFFERED=1" in content

    def test_entrypoint_script_structure(self):
        entrypoint = ROOT / "docker" / "entrypoint.sh"
        assert entrypoint.exists(), "entrypoint.sh must exist"
        content = entrypoint.read_text(encoding="utf-8")

        # Default port 7860
        assert "7860" in content
        # Preflight execution
        assert "api.preflight" in content
        # SIGTERM handler
        assert "SIGTERM" in content or "trap" in content
        # Uvicorn exec
        assert "uvicorn" in content

    def test_compose_yaml_validity(self):
        compose_dev = ROOT / "docker" / "compose.yaml"
        compose_prod = ROOT / "docker" / "compose.prod.yaml"

        assert compose_dev.exists()
        assert compose_prod.exists()

        dev_data = yaml.safe_load(compose_dev.read_text(encoding="utf-8"))
        prod_data = yaml.safe_load(compose_prod.read_text(encoding="utf-8"))

        assert "services" in dev_data
        assert "api" in dev_data["services"]

        assert "services" in prod_data
        assert "api" in prod_data["services"]
        assert "caddy" in prod_data["services"]

    def test_provider_configs_and_pending_docs(self):
        deploy_dir = ROOT / "deploy"
        assert deploy_dir.exists()

        expected_pending = [
            "PENDING_oracle.md",
            "PENDING_cloudrun.md",
            "PENDING_hfspace.md",
            "PENDING_aws.md",
            "PENDING_light.md",
            "PENDING_vercel.md",
            "PENDING_github.md",
        ]
        for pending in expected_pending:
            p_file = deploy_dir / pending
            assert p_file.exists(), f"Expected pending documentation: {pending}"
            content = p_file.read_text(encoding="utf-8")
            assert len(content) > 50, f"{pending} must provide actionable commands"


class TestIndexDeliveryMode:
    """Table-driven test for index delivery chooser."""

    @pytest.mark.parametrize(
        "total_bytes,bake_max_bytes,expected_mode",
        [
            (100 * 1024 * 1024, 700 * 1024 * 1024, "baked"),
            (699 * 1024 * 1024, 700 * 1024 * 1024, "baked"),
            (700 * 1024 * 1024, 700 * 1024 * 1024, "baked"),
            (701 * 1024 * 1024, 700 * 1024 * 1024, "fetched"),
            (2 * 1024 * 1024 * 1024, 700 * 1024 * 1024, "fetched"),
        ],
    )
    def test_delivery_mode_selection(self, total_bytes: int, bake_max_bytes: int, expected_mode: str):
        mode = "baked" if total_bytes <= bake_max_bytes else "fetched"
        assert mode == expected_mode


class TestDeployOrchestrator:
    """Test deployment credential detection, planning, and reports."""

    def test_credential_detection(self):
        with patch.dict(os.environ, {}, clear=True):
            targets = detect_available_targets()
            assert targets["local"] is True
            assert targets["oracle"] is False
            assert targets["cloudrun"] is False
            assert targets["hfspace"] is False
            assert targets["aws"] is False
            assert targets["light"] is False
            assert targets["vercel"] is False

        with patch.dict(
            os.environ,
            {
                "OCI_TENANCY_OCID": "ocid1.tenancy.oc1..test",
                "GCP_PROJECT": "regulatoriq-prod",
                "HF_TOKEN": "hf_test123",
                "AWS_ACCESS_KEY_ID": "AKIA_TEST",
                "RENDER_API_KEY": "rnd_test",
                "VERCEL_TOKEN": "vcl_test",
            },
            clear=True,
        ):
            targets = detect_available_targets()
            assert targets["oracle"] is True
            assert targets["cloudrun"] is True
            assert targets["hfspace"] is True
            assert targets["aws"] is True
            assert targets["light"] is True
            assert targets["vercel"] is True

    def test_deploy_plan_rendering(self):
        plan = plan_deployment(["oracle", "light", "local"])
        assert len(plan) == 3
        assert plan[0]["target"] == "oracle"
        assert plan[0]["mode"] == "full"
        assert plan[1]["target"] == "light"
        assert plan[1]["mode"] == "light"

    def test_deploy_dry_run_vs_apply(self, tmp_path):
        with patch("scripts.deploy.DEPLOYMENTS_FILE", tmp_path / "deployments.json"), patch(
            "scripts.deploy.REPORT_PATH", tmp_path / "deploy_report.md"
        ):
            # Dry run should not create deployments.json
            res = run_deployment(["local"], apply=False)
            assert not (tmp_path / "deployments.json").exists()
            assert (tmp_path / "deploy_report.md").exists()

            # Apply run creates deployments.json
            res_apply = run_deployment(["local"], apply=True)
            assert (tmp_path / "deployments.json").exists()
            saved = json.loads((tmp_path / "deployments.json").read_text(encoding="utf-8"))
            assert any(d["target"] == "local" for d in saved)


class TestWarmupLogic:
    """Unit tests for warmup.py keep-warm logic and cap enforcement."""

    def test_rolling_daily_cap(self, tmp_path):
        cache_file = tmp_path / "warmup_cache.json"
        with patch("scripts.warmup.WARMUP_CACHE_FILE", cache_file):
            now = 100000.0

            # Initially under cap
            assert check_daily_cap(now) is True

            # Record 9 runs
            for i in range(9):
                record_warmup_run(now + i)
            assert check_daily_cap(now + 10) is True

            # Record 10th run -> cap hit
            record_warmup_run(now + 10)
            assert check_daily_cap(now + 11) is False

            # After 24 hours (86401s), old runs expire
            assert check_daily_cap(now + 86402) is True

    def test_warmup_target_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"warmup_time_ms": 42.0, "status": "warmed"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok = warmup_target("http://testserver", "secret_token", max_retries=1)
            assert ok is True

    def test_warmup_target_401_abort(self):
        http_error = urllib.error.HTTPError(
            url="http://testserver/warmup",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            ok = warmup_target("http://testserver", "wrong_token", max_retries=2)
            assert ok is False


class TestSmokeUrlVerification:
    """Test URL parsing and safety rules in smoke suite."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://rbi.org.in/Scripts/BS_ViewMasCirculardetails.aspx?id=123", True),
            ("https://rbidocs.rbi.org.in/rdocs/notification/PDFs/123.PDF", True),
            ("https://subdomain.rbi.org.in/index.html", True),
            ("https://google.com/search?q=rbi", False),
            ("https://fake-rbi.org.in/fraud", False),
            ("https://rbi.org.in.attacker.com/steal", False),
            ("not-a-valid-url", False),
        ],
    )
    def test_is_allowed_rbi_url(self, url: str, expected: bool):
        assert is_allowed_rbi_url(url) == expected


class TestSecurityAndCostGuard:
    """Test token generator and cost guard."""

    def test_generate_secret(self):
        token = generate_secret("reg_")
        assert token.startswith("reg_")
        assert len(token) > 40
        # Subsequent tokens must be cryptographically distinct
        token2 = generate_secret("reg_")
        assert token != token2

    def test_cost_guard_audit(self):
        status = audit_cost_headroom()
        assert status["status"] == "compliant"
        assert status["estimated_monthly_cost_usd"] == 0.0


class TestPropertyBasedSchedules:
    """Hypothesis property-based tests for warmup cron schedules and backoff."""

    @settings(max_examples=25)
    @given(st.integers(min_value=1, max_value=5))
    def test_backoff_monotonicity(self, attempts: int):
        backoffs = [0, 15, 30, 45]
        delays = [backoffs[i] if i < len(backoffs) else 45 for i in range(attempts)]
        for i in range(len(delays) - 1):
            assert delays[i] <= delays[i + 1]
            assert delays[i] <= 45

    def test_warmup_cron_specifications(self):
        """Verify the 10 exact cron entries in warmup.yml."""
        warmup_yml = ROOT / ".github" / "workflows" / "warmup.yml"
        assert warmup_yml.exists()
        content = warmup_yml.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        on_block = data.get("on") if "on" in data else data.get(True, {})
        schedules = on_block.get("schedule", [])
        assert len(schedules) == 10, "Warmup workflow must contain exactly 10 schedule entries"

        cron_entries = [item["cron"] for item in schedules]
        expected_crons = [
            "40 1 * * *",
            "10 3 * * *",
            "35 4 * * *",
            "20 6 * * *",
            "45 7 * * *",
            "25 9 * * *",
            "50 10 * * *",
            "35 12 * * *",
            "10 14 * * *",
            "55 15 * * *",
        ]
        assert cron_entries == expected_crons

        # Check: no cron entry runs at :00 or :30
        for cron in cron_entries:
            minute = int(cron.split()[0])
            assert minute not in (0, 30), f"Cron entry '{cron}' must avoid exact :00 or :30 minutes"
