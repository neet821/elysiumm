# Root Impact Map Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the versioned release impact map from `deployment/release-impact.yml` to the repository root while keeping local tooling, CI, tests, and the production server consistent.

**Architecture:** `release-impact.yml` becomes a root-level repository policy file. All code defaults and CI staging commands resolve that canonical path; the server keeps the same policy file at `/srv/services/elysium/release-impact.yml`, while systemd, Nginx, release artifacts, and shared data remain in their existing external runtime locations.

**Tech Stack:** Python, Bash, GitHub Actions YAML, pytest, systemd deployment scripts.

**Spec:** User-approved request: modify local scripts, tests, GitHub Actions, and documentation; commit and test; update the server; verify impact map, release, and rollback flows; delete the server `deployment/` directory only after verification.

## Global Constraints

- Do not modify FlClash or FlClashCore.
- Do not change backend/frontend release contents or shared data.
- Do not delete baseline, release history, or rollback archives.
- The server migration must be atomic and reversible until final verification passes.
- The old `deployment/release-impact.yml` path must not remain as an active or fallback path.

---

### Task 1: Establish migration contract and regression tests

**Files:**
- Create: `release-impact.yml` (moved from `deployment/release-impact.yml`)
- Modify: `tests/test_release_impact.py`
- Modify: `tests/test_production_deploy.py`

**Interfaces:**
- The default impact map path is `<repository-root>/release-impact.yml`.
- Explicit `--impact-map` paths continue to work for temporary test fixtures.

- [ ] **Step 1: Add tests asserting the canonical root path and rejecting the old default path.**
- [ ] **Step 2: Run the focused tests and confirm they fail because implementation still defaults to `deployment/release-impact.yml`.**
- [ ] **Step 3: Move the policy file to the repository root and update test fixtures to copy it from that location.**
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 2: Update tooling and CI references

**Files:**
- Modify: `scripts/resolve-release-impact.py`
- Modify: `scripts/deploy-production.py`
- Modify: `deployment/production_deploy.py`
- Modify: `.github/workflows/deploy.yml`
- Modify: `deployment/release-impact.yml` before moving, so its self-reference points to `release-impact.yml`

**Interfaces:**
- CI stages `release-impact.yml` at the server root.
- Deployment code accepts an explicit map path and defaults to the root-level map.

- [ ] **Step 1: Change all defaults, staging paths, changed-path fallback, and self-references to `release-impact.yml`.**
- [ ] **Step 2: Run the focused resolver and deployment tests.**
- [ ] **Step 3: Run shell syntax checks for changed workflow-adjacent scripts.**

### Task 3: Update operational documentation

**Files:**
- Modify: `docs/deployment.md`
- Modify: `docs/operations/release-cicd.md`
- Modify: `docs/superpowers/plans/2026-09-12-release-cicd.md`

- [ ] **Step 1: Replace active-path references with the root-level `release-impact.yml` path.**
- [ ] **Step 2: Document that the server root keeps the policy file while deployment scripts are staged temporarily.**
- [ ] **Step 3: Scan the repository and confirm no active reference still points to `deployment/release-impact.yml`.**

### Task 4: Local verification and commit

**Files:**
- Modify only files from Tasks 1–3.

- [ ] **Step 1: Run focused release-impact and production-deploy tests.**
- [ ] **Step 2: Run the impact resolver against `origin/main` and `HEAD`.**
- [ ] **Step 3: Run release-gate and compile checks appropriate to the local environment.**
- [ ] **Step 4: Review `git diff`, status, and changed-file scope.**
- [ ] **Step 5: Commit the migration on `main`.**

### Task 5: Atomic server migration and verification

**Files:**
- Server `/srv/services/elysium/release-impact.yml`
- Server `/srv/services/elysium/deployment/` (remove only after successful verification)

- [ ] **Step 1: Confirm the server repository and current links before mutation.**
- [ ] **Step 2: Upload the committed root-level policy file to a temporary path and validate YAML/impact resolution.**
- [ ] **Step 3: Install it atomically at the server root and retain a rollback copy outside the service root.**
- [ ] **Step 4: Verify release preflight, release creation dry-run, and rollback transaction path use the root policy.**
- [ ] **Step 5: Confirm no active server script or configuration references the old path.**
- [ ] **Step 6: Remove the now-empty server `deployment/` directory only after Steps 2–5 pass.**
- [ ] **Step 7: Re-run final checks and record exact current links and transaction state.**

### Task 6: Final acceptance

- [ ] Confirm local `main`, GitHub `origin/main`, server `repository.git`, and the deployed policy file refer to the same commit contents.
- [ ] Confirm backend/frontend current links remain unchanged.
- [ ] Confirm shared data, baseline, release history, systemd, Nginx, MediaMTX, and health guard remain unchanged.
- [ ] Report any verification that could not be performed without a production deployment or maintenance window.
