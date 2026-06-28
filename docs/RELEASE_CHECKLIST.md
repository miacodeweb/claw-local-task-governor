# Release Checklist - v0.1.0-rc1

Follow these steps before tagging the local release candidate. **Codex must NOT run `git push`, `git tag`, publish to PyPI, or create a GitHub release without explicit permission.**

## 1. Manual Smoke Checks

```powershell
python -m pip install -e .
localscope --help
localscope audit tests/fixtures/sample_project --max-tasks 3 --dry-run
localscope providers list
localscope model-recommendations
localscope logs summary
localscope webui --help
```

If `localscope` is not on PATH on Windows:

```powershell
# Diagnose
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
python -c "import shutil; print(shutil.which('localscope'))"

# Test with full path
Test-Path "$env:APPDATA\Python\Python314\Scripts\localscope.exe"
& "$env:APPDATA\Python\Python314\Scripts\localscope.exe" --help
```

Add `%APPDATA%\Python\Python314\Scripts` to PATH via System Properties, or use `python -m governor.main`.

## 2. Tests

```powershell
pytest tests/test_release_smoke.py tests/test_release_files.py tests/test_main.py
pytest
```

## 3. Verify git status

```powershell
git status --short
```

Expected: no `logs/`, `reports/`, `data/`, `.env`, `*.sqlite`, build output, or egg-info files are staged.

## 4. Verify .gitignore

Must exclude: `logs/`, `reports/`, `data/`, `*.sqlite`, `.env`, `.env.*`, `__pycache__/`, `.pytest_cache/`, `.venv/`, `node_modules/`, `dist/`, `build/`, `*.egg-info/`.

## 5. Verify Version

Check `pyproject.toml`:

```toml
version = "0.1.0rc1"
```

The Git tag format should be:

```powershell
git tag v0.1.0-rc1
```

## 6. Verify Snapshot Files Exist

- [ ] `CHANGELOG.md`
- [ ] `SECURITY.md`
- [ ] `CONTRIBUTING.md`
- [ ] `LICENSE`
- [ ] `README.md`
- [ ] `PROJECT_BRIEF.md`
- [ ] `docs/RELEASE_MVP.md`
- [ ] `docs/RELEASE_CHECKLIST.md`
- [ ] `docs/RC1_TEST_PLAN.md`
- [ ] `.github/ISSUE_TEMPLATE/bug_report.yml`
- [ ] `.github/ISSUE_TEMPLATE/feature_request.yml`
- [ ] `.github/PULL_REQUEST_TEMPLATE.md`

## 7. Do Not Publish From This Checklist

Do not run:

```powershell
git push
python -m build
twine upload
```

Do not create a GitHub release until the stable v0.1.0 release is explicitly approved.
