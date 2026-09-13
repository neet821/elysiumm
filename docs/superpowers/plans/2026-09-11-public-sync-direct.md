# Elysium Public Sync via FlClash Direct Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore `/home/neet821/Public` synchronization to the deployed Elysium site while sending the client through FlClash's local `127.0.0.1:7890` port and routing only the Elysium domain directly.

**Architecture:** Keep the existing Elysium `/api/sync/*` protocol and client-side file-delta logic. Run the Elysium client with an explicit HTTP proxy at `127.0.0.1:7890`; add a minimal `DOMAIN-SUFFIX,elysiumm.top,DIRECT` rule to the active FlClash profile so the core forwards this traffic directly instead of using an airport node.

**Tech Stack:** Python 3.14 standard library, urllib proxy handler, user systemd, FlClash/Mihomo rules, Elysium FastAPI public-sync API.

**Spec:** User request: sync `/home/neet821/Public` to the new website; all local traffic may pass through FlClash core at `127.0.0.1:7890`, while the client rule must decide whether the destination uses an airport node.

## Global Constraints

- Do not restart FlClashCore; make only the single Elysium domain rule change in the active profile.
- Do not delete or overwrite files in `/home/neet821/Public`.
- Keep the existing Elysium API contract and `X-Sync-Token` authentication.
- Only the Elysium sync unit may be enabled; old Blue Album sync units remain removed.
- Verify the agent connects to `127.0.0.1:7890` and FlClash classifies Elysium as `DIRECT`.

### Task 1: Proxy transport

**Files:**
- Modify: `tools/public-sync-agent/public_sync_agent.py`
- Test: `backend/tests/test_public_sync_agent_unittest.py`

- [x] Add an explicit `PUBLIC_SYNC_PROXY` proxy handler using `http://127.0.0.1:7890`, avoiding inherited or ambient proxy ambiguity.
- [x] Make all heartbeat, chunk, delete, and error calls use that handler.
- [x] Preserve chunking, SHA-256 checks, state tracking, pause handling, and remote deletion semantics.
- [x] Run the focused agent tests and a no-token proxied heartbeat probe.

### Task 2: FlClash direct rule

**Files:**
- Existing client additional-rule configuration (no file change)

- [x] Confirm the existing client additional rule `elysiumm.top → DIRECT`; no FlClash file or core restart was needed.

### Task 3: Elysium user service

**Files:**
- Create: `/home/neet821/.config/elysium/public-sync.env`
- Create: `/home/neet821/.config/systemd/user/elysium-public-sync.service`

- [x] Configure the Elysium endpoint, existing sync token, state path, interval, and `127.0.0.1:7890` proxy without printing the token.
- [x] Run the Elysium copy of the agent from the user systemd unit.
- [x] Enable and start only this unit.

### Task 4: Backend idempotency

**Files:**
- Modify: `backend/public_sync_service.py`
- Test: `backend/tests/test_public_sync_service_unittest.py`

- [x] Reuse the pending `SyncFile` record when a one-chunk upload completes, preventing duplicate-path inserts.
- [x] Add and pass a regression test for a new one-chunk file.
- [x] Back up and deploy the single backend file to the active release; restart only `elysiumm-backend.service`.

### Task 5: Verify runtime path

- [x] Confirm the service is active and the old Blue Album units remain absent.
- [x] Confirm the agent reaches Elysium and produces no SSL/proxy errors.
- [x] Confirm the agent is configured for `127.0.0.1:7890` and the Elysium rule is `DIRECT`.
- [x] Confirm no FlClashCore restart occurred and no FlClash file changed.
- [x] Confirm both Public files are `synced` remotely with matching SHA-256 values.
