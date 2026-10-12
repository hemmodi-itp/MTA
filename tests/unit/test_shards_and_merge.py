"""Phase 4.8 — shard planning (tools/execution/shards.py) and blob merging (tools/execution/merge_reports.py)."""

import os

import pytest

from tools.execution import merge_reports as mr
from tools.execution.shards import ShardSpecError, blob_root, parse_shard, plan_shards, shard_blob_dir, single_shard

CMD = ["npx", "playwright", "test", "a/M01", "--config", "playwright.config.ts", "--project=chromium",
       "--workers=2", "--output=r/test-results/T"]


def test_parse_shard():
    assert parse_shard("2/3") == (2, 3)
    assert parse_shard(" 1 / 1 ") == (1, 1)
    assert parse_shard(None) is None and parse_shard("") is None
    for bad in ("0/3", "4/3", "x", "1/0", "1-2"):
        with pytest.raises(ShardSpecError):
            parse_shard(bad)


def test_plan_shards_gives_each_shard_its_own_blob_and_output_folder():
    runs = plan_shards(CMD, {"A": "1"}, 2, "r", "RUN", "r/test-results/T")
    assert [r.index for r in runs] == [1, 2]
    for r in runs:
        assert r.cmd[-1] == f"--shard={r.index}/2"
        outs = [a for a in r.cmd if a.startswith("--output=")]
        assert outs == ["--output=" + os.path.join("r/test-results/T", f"shard-{r.index}")]
        assert r.env["PW_BLOB_DIR"] == shard_blob_dir("r", "RUN", r.index)
        assert r.env["MTA_BLOB_ONLY"] == "1" and r.env["A"] == "1"
    assert runs[0].blob_dir != runs[1].blob_dir            # the blob reporter empties its folder
    assert runs[0].output_dir != runs[1].output_dir        # Playwright empties --output at start
    assert CMD[-1] == "--output=r/test-results/T"          # input not mutated


def test_single_shard_keeps_normal_reporters_and_adds_a_blob():
    cmd, env = single_shard(CMD, {"X": "y"}, 1, 2, "r", "RUN")
    assert cmd[-1] == "--shard=1/2" and "MTA_BLOB_ONLY" not in env
    assert env["PW_BLOB_DIR"] == os.path.join(blob_root("r", "RUN"), "shard-1")
    _, env2 = single_shard(CMD, {}, 1, 2, "r", "RUN", invocation="T1")
    assert env2["PW_BLOB_DIR"] == os.path.join(blob_root("r", "RUN"), "shard-1-T1")


def test_collect_blobs_copies_every_shard_zip_into_one_folder(tmp_path):
    for i in (1, 2):
        d = tmp_path / f"shard-{i}"
        d.mkdir()
        (d / f"report-{i}.zip").write_bytes(b"zip" + bytes([i]))
    target, names = mr.collect_blobs(str(tmp_path))
    assert sorted(names) == ["report-1.zip", "report-2.zip"]
    assert sorted(os.listdir(target)) == ["report-1.zip", "report-2.zip"]
    _, again = mr.collect_blobs(str(tmp_path))               # re-collect: the input folder is rebuilt, not nested
    assert sorted(again) == ["report-1.zip", "report-2.zip"]


def test_collect_blobs_never_overwrites_a_same_named_zip(tmp_path):
    for job in ("job-a", "job-b"):
        d = tmp_path / job
        d.mkdir()
        (d / "report.zip").write_bytes(job.encode())
    _, names = mr.collect_blobs(str(tmp_path))
    assert len(names) == 2 and "report.zip" in names


def test_merge_command_and_env():
    assert mr.merge_command("r/blob/RUN/_merge_input") == [
        "npx", "playwright", "merge-reports", "--config", "playwright.merge.config.ts", "r/blob/RUN/_merge_input"]
    env = mr.merge_env({"PW_BLOB_DIR": "x", "MTA_BLOB_ONLY": "1", "PW_JUNIT_REPORT": "old", "KEEP": "1"},
                       json_path="j.json", html_dir="h", junit_path="", mta_path="m.json")
    assert env["PW_JSON_REPORT"] == "j.json" and env["PW_HTML_REPORT"] == "h" and env["MTA_RESULTS_FILE"] == "m.json"
    assert "PW_BLOB_DIR" not in env and "MTA_BLOB_ONLY" not in env and "PW_JUNIT_REPORT" not in env
    assert env["KEEP"] == "1"


def test_merge_blob_reports_without_blobs_skips_the_merge(tmp_path):
    calls = []
    names, (_o, err, _i, rc) = mr.merge_blob_reports(str(tmp_path), {}, lambda *a: calls.append(a))
    assert names == [] and rc == 1 and "no blob reports" in err and calls == []


def test_merge_blob_reports_runs_merge_reports(tmp_path):
    (tmp_path / "shard-1").mkdir()
    (tmp_path / "shard-1" / "report-1.zip").write_bytes(b"z")
    seen = {}

    def run(cmd, cwd, env):
        seen.update(cmd=cmd, env=env)
        return "out", "", False, 0

    names, (out, _e, _i, rc) = mr.merge_blob_reports(str(tmp_path), {"PW_JSON_REPORT": "j"}, run)
    assert names == ["report-1.zip"] and rc == 0 and out == "out"
    assert seen["cmd"][:4] == ["npx", "playwright", "merge-reports", "--config"]
    assert seen["cmd"][-1].endswith("_merge_input")
