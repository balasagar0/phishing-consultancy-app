"""Copies the detection engine from the CP1 project's tag cp1-final into engine/, read-only, and records every file's hash.
  python scripts/sync_engine.py [--project ../project] [--tag cp1-final]      copy (replaces engine/)
  python scripts/sync_engine.py --verify                                       check engine/ against its manifest and against the tag's model manifest
The project is never changed: files are read with `git archive` and `git show`. The app runs this pinned copy, so its scores are the scores
of cp1-final (tests/test_engine_parity.py checks the eight demo cases to three decimals)."""
import argparse, datetime, hashlib, io, json, shutil, subprocess, sys, tarfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]; ENGINE = APP / "engine"
FILES = ["api.py", "src/common.py", "src/predict.py", "src/fusion.py", "src/event_store.py", "src/url_features.py", "src/demo_cases.py",
         "models/email_model.joblib", "models/sms_model.joblib", "models/url_string_model.joblib", "models/fusion_model.joblib",
         "requirements.txt", "tests/test_demo_cases.py"]
NUMBERS = "reports/final_numbers.json"      # written from cp1-final by the project's scripts/make_final_numbers.py, committed after the tag


def sha256(b): return hashlib.sha256(b).hexdigest()


def git(project, *a, binary=False):
    r = subprocess.run(["git", "-C", str(project), *a], capture_output=True)
    if r.returncode: sys.exit(f"git {' '.join(a)} failed: {r.stderr.decode(errors='replace')[:300]}")
    return r.stdout if binary else r.stdout.decode().strip()


def sync(project, tag):
    commit = git(project, "rev-parse", f"{tag}^{{commit}}")
    tar = git(project, "archive", "--format=tar", commit, "--", *FILES, binary=True)
    if ENGINE.exists(): shutil.rmtree(ENGINE)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            if not m.isfile(): continue
            if m.name not in FILES: sys.exit(f"unexpected file in archive: {m.name}")
            data = t.extractfile(m).read(); dst = ENGINE / m.name
            dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(data); files[m.name] = {"bytes": len(data), "sha256": sha256(data)}
    missing = set(FILES) - set(files)
    if missing: sys.exit(f"missing from {tag}: {sorted(missing)}")
    num_commit = git(project, "log", "-1", "--format=%H", "main", "--", NUMBERS)
    nums = git(project, "show", f"{num_commit}:{NUMBERS}", binary=True)
    if json.loads(nums)["build"]["commit"] != commit: sys.exit(f"{NUMBERS} at {num_commit[:7]} was not written from {tag}")
    (ENGINE / "final_numbers.json").write_bytes(nums); files["final_numbers.json"] = {"bytes": len(nums), "sha256": sha256(nums)}
    tag_models = json.loads(git(project, "show", f"{commit}:reports/model_manifest.json"))
    man = {"source": "CP1 project (separate folder, read-only)", "tag": tag, "tag_commit": commit, "numbers_commit": num_commit,
           "synced_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "files": files,
           "tag_model_manifest": {k: v for k, v in tag_models.items() if k != "generated"} if isinstance(tag_models, dict) else tag_models}
    (ENGINE / "ENGINE_MANIFEST.json").write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    print(f"engine/ synced from {tag} ({commit[:7]}): {len(files)} files; numbers from {num_commit[:7]}")
    return verify()


def verify():
    mp = ENGINE / "ENGINE_MANIFEST.json"
    if not mp.exists(): print("engine/ENGINE_MANIFEST.json is missing: run scripts/sync_engine.py"); return 1
    man = json.loads(mp.read_text(encoding="utf-8")); bad = []
    for rel, info in man["files"].items():
        p = ENGINE / rel
        if not p.exists() or sha256(p.read_bytes()) != info["sha256"]: bad.append(rel)
    tagm = json.dumps(man.get("tag_model_manifest", ""))
    for rel, info in man["files"].items():
        if rel.startswith("models/") and info["sha256"] not in tagm: bad.append(rel + " (not the hash the tag's model manifest lists)")
    print("engine verified: every file matches cp1-final" if not bad else f"engine does NOT match: {bad}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", default=str(APP.parent / "project")); ap.add_argument("--tag", default="cp1-final")
    ap.add_argument("--verify", action="store_true"); a = ap.parse_args()
    sys.exit(verify() if a.verify else sync(Path(a.project), a.tag))


if __name__ == "__main__":
    main()
