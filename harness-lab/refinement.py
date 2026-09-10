"""Bounded act/refine orchestration; Rust owns eligibility and artifact policy."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

import artifacts
import buck_host
import workspace as workspace_module


class TransportIntegrityError(workspace_module.WorkspaceError):
    def __init__(self, message: str):
        super().__init__(message, indeterminate=True)


class Manager:
    def __init__(
        self,
        session,
        workspace,
        store: artifacts.Store,
        initial: dict,
        condition: str,
        attempt_id: str,
        refiner: Callable,
        instructions: str,
    ):
        self.session = session
        self.workspace = workspace
        self.store = store
        self.current = store.read(initial["revision_sha256"])
        self.condition = condition
        self.attempt_id = attempt_id
        self.refiner = refiner
        self.instructions = instructions
        self.pairs: list[dict] = []
        self.receipts: list[dict] = []
        self.terminal_error: str | None = None
        self._boundaries: set[int] = set()
        self.directory = session.directory / "refinement"
        self.directory.mkdir(exist_ok=False)

    def observe(self, operation: str, args: dict, result: dict) -> None:
        # Snapshot the native boundary, before learned-context annotations.
        pair = json.loads(
            artifacts.canonical(
                buck_host._safe_json(
                    {
                        "request": {
                            "sequence": len(self.pairs) + 1,
                            "operation": operation,
                            "arguments": args,
                        },
                        "response": result,
                    }
                )
            )
        )
        self.pairs.append(pair)
        artifacts.write_once(
            self.directory / f"observation-{len(self.pairs):06d}.json", pair
        )
        if self.terminal_error:
            raise TransportIntegrityError(self.terminal_error)
        if result.get("mutation_committed") is True:
            policy = artifacts.judge(
                "refinement.eligible",
                {
                    "successful_mutations": self.session.actions,
                    "measurement_complete": result.get("native_verdict")
                    in ("pass", "fail"),
                    "construction_passed": result.get("native_verdict") == "pass",
                    "deadline_expired": time.monotonic() >= self.session.deadline,
                    "refinement_count": len(self.receipts),
                    "condition": self.condition,
                },
            )
            if policy["eligible"] and self.session.actions not in self._boundaries:
                self._boundaries.add(self.session.actions)
                self._refine(result, policy["max_refiner_ms"] / 1000)
        result["learned_revision"] = self.current["revision_sha256"]
        result["notes"] = self.current["notes_utf8"]

    def _refine(self, observation: dict, maximum_seconds: float) -> None:
        started = time.monotonic()
        deadline = min(
            self.session.deadline,
            started + maximum_seconds,
            getattr(self.session, "_active_cell_deadline", None)
            or self.session.deadline,
        )
        directory = self.directory / f"boundary-{self.session.actions}"
        directory.mkdir(exist_ok=False)
        receipt = {
            "boundary": self.session.actions,
            "parent_revision_sha256": self.current["revision_sha256"],
            "board_sha256": self.session.revision,
            "deadline": deadline,
            "status": "skipped",
        }
        try:
            if deadline <= started:
                raise TimeoutError("no refinement time remains")
            context = artifacts.judge(
                "context.build",
                {
                    "notes_utf8": self.current["notes_utf8"],
                    "skills_utf8": self.current["skills_utf8"],
                    "observation": observation,
                    "instructions": self.instructions,
                    "pairs": self.pairs,
                },
                timeout=min(5, deadline - time.monotonic()),
            )
            artifacts.write_once(directory / "context.json", context)
            proposal = self.refiner(context["context"], deadline, directory)
            artifacts.write_once(
                directory / "proposal.json", buck_host._safe_json(proposal)
            )
            if not isinstance(proposal, dict) or set(proposal) != {
                "notes_utf8",
                "skills_utf8",
                "model",
                "transport",
            }:
                raise ValueError(
                    "refiner must return complete artifacts and transport evidence"
                )
            transport = proposal["transport"]
            if (
                proposal["model"] != artifacts.MODEL
                or not isinstance(transport, dict)
                or transport.get("verified") is not True
            ):
                raise TransportIntegrityError(
                    "refiner model/transport was not verified"
                )
            receipt["transport"] = transport
            if time.monotonic() >= deadline:
                raise TimeoutError("refinement deadline expired")
            reference = transport.get("reference")
            if (
                not isinstance(reference, str)
                or Path(reference).is_absolute()
                or ".." in Path(reference).parts
            ):
                raise TransportIntegrityError(
                    "refiner transport reference escaped its directory"
                )
            count = context["pair_count"]
            first = context["trimmed_pair_count"] + 1 if count else 0
            last = len(self.pairs) if count else 0
            payload = {
                "attempt_id": self.attempt_id,
                "parent_revision_sha256": self.current["revision_sha256"],
                "source_window": {
                    "first_sequence": first,
                    "last_sequence": last,
                    "pair_count": count,
                    "window_sha256": context["window_sha256"],
                },
                "source_pairs": context["context"]["pairs"],
                "notes_utf8": proposal["notes_utf8"],
                "skills_utf8": proposal["skills_utf8"],
                "proposal_model": proposal["model"],
                "proposal_transport_ref": reference,
                "application_boundary": f"after_measurement_{self.session.actions}",
            }
            child = self.store.propose(payload)
            receipt["child_revision_sha256"] = child["revision_sha256"]
            applied = self.workspace.apply_revision(
                child["revision_sha256"],
                child["skills_utf8"],
                child["notes_utf8"],
                deadline=deadline,
            )
            if not applied:
                raise ValueError(
                    "skills module initialization failed; old revision retained"
                )
            self.current = child
            receipt["status"] = "applied"
            receipt["context_sha256"] = context["context_sha256"]
        except TransportIntegrityError as error:
            receipt.update(status="indeterminate", reason=str(error))
            self.terminal_error = str(error)
            self.workspace._terminate(self.terminal_error)
            raise
        except workspace_module.WorkspaceError as error:
            receipt.update(status="indeterminate", reason=str(error))
            self.terminal_error = str(error)
            raise
        except (ValueError, TypeError, KeyError, SyntaxError, TimeoutError) as error:
            receipt.update(status="rejected", reason=f"{type(error).__name__}: {error}")
        finally:
            receipt["elapsed_s"] = time.monotonic() - started
            receipt["active_revision_sha256"] = self.current["revision_sha256"]
            self.receipts.append(receipt)
            artifacts.write_once(directory / "receipt.json", receipt)
