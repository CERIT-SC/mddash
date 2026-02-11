"""
Background simulator for demo API.

Handles state transitions like pod startup, job progress, etc.
"""

import random
import threading
import time
from typing import Optional
from uuid import uuid4

from state import state


class DemoSimulator:
    """Simulates background processes and state transitions."""

    def __init__(self) -> None:
        """Initialize the simulator with stopped state."""
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the simulator thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        """Stop the simulator thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _run(self) -> None:
        """Run the main simulation loop."""
        while self.running:
            try:
                self._simulate_notebooks()
                self._simulate_tuner_jobs()
                self._simulate_gromacs_jobs()
                time.sleep(1)
            except Exception as e:
                print(f"Simulator error: {e}")

    def _simulate_notebooks(self) -> None:
        """Simulate notebook state transitions."""
        for exp in state.experiments.values():
            notebook = exp["notebook"]
            status = notebook["status"]
            start_time = notebook.get("start_time")

            # PENDING -> RUNNING (simulate pod startup, 5-10 seconds)
            if status == "PENDING" and start_time:
                elapsed = time.time() - start_time
                if elapsed > random.uniform(5, 10):
                    notebook["status"] = "RUNNING"

    def _simulate_tuner_jobs(self) -> None:
        """Simulate tuner job state transitions."""
        for exp in state.experiments.values():
            for tuner in exp["tuner_jobs"]:
                # Skip tuners that are errored or stopped
                if tuner["error_message"] or tuner.get("is_stopped"):
                    continue

                start_time = tuner.get("start_time")
                if not start_time:
                    continue

                # Gradually add trials for newly-started tuner runs.
                trials_to_add = tuner.get("trials_to_add") or 0
                if trials_to_add and len(tuner.get("trials", [])) < trials_to_add:
                    last_added = tuner.get("last_trial_added_at") or start_time
                    # Add one trial every ~2-10 seconds (randomized)
                    if time.time() - last_added > random.uniform(2, 10):
                        new_id = f"{(tuner.get('tuner_run_id') or str(uuid4()))[:5]}_{len(tuner['trials']):05d}"
                        new_trial = {
                            "id": new_id,
                            "status": "RUNNING",
                            "np": 2,
                            "ntomp": random.choice([1, 2, 4, 8]),
                            "nb": "cpu",
                            "pme": "cpu",
                            "performance": None,
                        }
                        tuner.setdefault("trials", []).append(new_trial)
                        tuner["last_trial_added_at"] = time.time()

                # Simulate running trials completion (10-20 seconds)
                for trial in list(tuner.get("trials", [])):
                    if trial["status"] == "RUNNING":
                        trial_start = trial.get("start_time", start_time)
                        if time.time() - trial_start > random.uniform(10, 20):
                            trial["status"] = "TERMINATED"
                            trial["performance"] = round(random.uniform(10.0, 500.0), 3)

                # If we've added all trials and none are running, mark tuner as terminated
                total_expected = tuner.get("trials_to_add", 0) or 0
                current_total = len(tuner.get("trials", []))
                running_count = sum(1 for t in tuner.get("trials", []) if t["status"] == "RUNNING")
                if total_expected > 0 and current_total >= total_expected and running_count == 0:
                    tuner["tuner_status"] = "TERMINATED"
                    tuner["is_stopped"] = True

    def _simulate_gromacs_jobs(self) -> None:
        """Simulate GROMACS job progress."""
        for exp in state.experiments.values():
            for job in exp["gromacs_jobs"]:
                if job["status"] != "RUNNING":
                    continue

                start_time = job.get("start_time")
                if not start_time:
                    continue

                elapsed = time.time() - start_time
                nsteps = job["nsteps"]

                # Simulate progress (complete in ~30 seconds)
                progress_rate = nsteps / 30.0
                expected_steps = int(elapsed * progress_rate)
                job["nsteps_done"] = min(expected_steps, nsteps)

                # Calculate estimated time remaining
                if job["nsteps_done"] > 0:
                    steps_remaining = nsteps - job["nsteps_done"]
                    time_per_step = elapsed / job["nsteps_done"]
                    job["estimated_time"] = int(steps_remaining * time_per_step)

                # Mark as TERMINATED when complete
                if job["nsteps_done"] >= nsteps:
                    job["status"] = "TERMINATED"
                    job["performance"] = round(random.uniform(40.0, 80.0), 3)
                    job["estimated_time"] = 0


# Global simulator instance
simulator = DemoSimulator()
