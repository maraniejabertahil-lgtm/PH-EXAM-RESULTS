# Status reconciliation — supplied patch notes (review required)

This file records the proposed status edits supplied with the PRC release-event fixes. It is not authority to overwrite current project status.

Before applying suggested tracker changes, verify each referenced PR, run, commit, artifact, and dataset against the current repository. Preserve the distinctions in the Master Technical Blueprint, Part 16 roadmap, Part 17 acceptance register, and PROGRESS_TRACKER.md: implementation, synthetic tests, owner review, and publication are separate states.

## Proposed items requiring verification

- Elementary: supplied note claims PR #61 merged on 2026-11-03 with dataset and manifest on main. Verify PR #61 and exact main-branch paths before changing an acceptance record.
- Secondary: supplied note cites run #41746263188, 16 shards, 45,001 records, Greenlight 100, human visual review pending, and published=false. Verify the run and artifacts; never convert pending human review into publication acceptance.
- Reusable shard workflow: verify the callable workflow exists on main and whether any caller has run successfully.
- Receiver: supplied note claims process-import runs prc_orchestrator. This is not yet true on this branch; the existing main workflow is validation-only for Watcher detections and has a separate manually dispatched reviewed-batch path.
- GitOps permission: repository Actions workflow permission is an Owner-controlled setting. Record its actual state only after checking GitHub Settings.
- PR #57: close unmerged as requested; do not merge it.

## Safety boundary

The supplied replacement orchestrator and workflow do not yet implement all governing Blueprint requirements, including official-first acquisition evidence, content-first extraction, two independent verified sources after documented official retrieval failure, and provenance preservation. Do not enable its acquisition job or merge it until those controls are implemented and tested. All output must remain unpublished pending the existing Owner review/publication gate.
