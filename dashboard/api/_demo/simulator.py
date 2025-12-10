"""
Background simulator for demo API.

Handles state transitions like pod startup, job progress, etc.
"""

import random
import threading
import time
from typing import Optional

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
                if tuner["is_pending"] or tuner["error_message"] or tuner["is_stopped"]:
                    continue

                start_time = tuner.get("start_time")
                if not start_time:
                    continue

                # Simulate running trials completion (30-60 seconds)
                for trial in tuner["trials"]:
                    if trial["status"] == "RUNNING":
                        trial_start = trial.get("start_time", start_time)
                        if time.time() - trial_start > random.uniform(30, 60):
                            trial["status"] = "TERMINATED"
                            trial["performance"] = round(random.uniform(40.0, 80.0), 3)

                # Update cluster resources based on running trials
                running_count = sum(1 for t in tuner["trials"] if t["status"] == "RUNNING")
                if running_count > 0:
                    cpus_used = running_count * 8
                    tuner["cluster_resources"] = f"{cpus_used}/32 CPUs, 0/1 GPUs used"
                else:
                    tuner["cluster_resources"] = "0/32 CPUs, 0/1 GPUs used"

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
