"""AMBER mdin file patcher for benchmark runs."""

import re
from typing import Any

from api.engines.amber.config import EwaldPreset


def simulation_length_ns(content: str) -> float | None:
    """Production simulation length (ns) from an mdin file: nstlim * dt. None if unparsable."""
    nstlim = _read_param(content, "nstlim")
    dt = _read_param(content, "dt")
    if nstlim is None or dt is None:
        return None
    return float(nstlim) * dt / 1000.0  # dt is in ps


def _read_param(content: str, key: str) -> float | None:
    """Read a numeric `key = value,` namelist parameter (case-insensitive)."""
    match = re.search(
        rf"^\s*{re.escape(key)}\s*=\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)\s*,?",
        content,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return float(match.group(1)) if match else None


def patch_mdin_for_benchmark(content: str, nsteps: int, ewald: EwaldPreset) -> str:
    """
    Patch an AMBER mdin file for benchmarking.

    Overrides output-frequency and step-count params only.
    All physics parameters (ensemble, temperature, pressure, constraints) are preserved.
    """
    cntrl_overrides = {
        "nstlim": nsteps,
        "ntwx": 0,
        "ntwr": 0,
        "ntave": 0,
        "ntpr": min(nsteps, 5000),
    }
    content = _patch_namelist(content, "&cntrl", cntrl_overrides)

    if ewald == EwaldPreset.OPTIMIZED:
        ewald_overrides: dict[str, int | float] = {"netfrc": 0, "skin_permit": 0.75}
        if "&ewald" in content.lower():
            content = _patch_namelist(content, "&ewald", ewald_overrides)
        else:
            content = _append_namelist(content, "&ewald", ewald_overrides)

    return content


def _patch_namelist(content: str, namelist: str, overrides: dict[str, Any]) -> str:
    """Remove existing override keys inside namelist, then inject new values before closing '/'."""
    lines = content.splitlines()
    result: list[str] = []
    in_block = False

    for line in lines:
        stripped = line.strip().lower()

        if stripped == namelist.lower():
            in_block = True
            result.append(line)
            continue

        if in_block and stripped == "/":
            for key, value in overrides.items():
                result.append(f"  {key} = {value},")
            in_block = False

        if in_block:
            # Strip existing occurrences of keys we're injecting
            cleaned = _remove_param(line, set(overrides.keys()))
            if cleaned.strip():
                result.append(cleaned)
        else:
            result.append(line)

    return "\n".join(result) + "\n"


def _append_namelist(content: str, namelist: str, params: dict[str, Any]) -> str:
    """Append a new namelist block at the end of the mdin content."""
    lines = [f" {namelist}"]
    for key, value in params.items():
        lines.append(f"  {key} = {value},")
    lines.append(" /")
    return content.rstrip() + "\n" + "\n".join(lines) + "\n"


def _remove_param(line: str, keys: set[str]) -> str:
    """Remove any 'key = value,' occurrences from a line for the given keys."""
    for key in keys:
        line = re.sub(
            rf"\b{re.escape(key)}\s*=\s*[^\s,]+,?\s*",
            "",
            line,
            flags=re.IGNORECASE,
        )
    return line
