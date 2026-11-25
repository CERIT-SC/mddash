import type {
  AmberJobRequest,
  GromacsJobRequest,
  GromacsJobRequestNb,
  GromacsJobRequestPme,
} from "@/api/generated/models"
import { Engine } from "@/api/generated/models"

import type { HardwareConfigValues } from "./hardware-config-form"

// Maps to the production-run request body: pickA = pme/binary, pickB = nb/ewald.
// Select options plus Zod keep strings inside the engine enums, hence the casts.
export function toJobRequest(engine: Engine, values: HardwareConfigValues): GromacsJobRequest | AmberJobRequest {
  if (engine === Engine.AMBER) {
    return { binary: values.pickA, ewald: values.pickB, np: values.np, ntomp: values.ntomp }
  }
  return {
    pme: values.pickA as GromacsJobRequestPme,
    nb: values.pickB as GromacsJobRequestNb,
    np: values.np,
    ntomp: values.ntomp,
  }
}

/** Seeds the hardware form from a run request (the inverse of toJobRequest). */
export function toHardwareValues(request: GromacsJobRequest | AmberJobRequest): HardwareConfigValues {
  const picks =
    "binary" in request ? { pickA: request.binary, pickB: request.ewald } : { pickA: request.pme, pickB: request.nb }
  return { ...picks, np: request.np, ntomp: request.ntomp }
}

const count = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`

/** One line naming a run configuration, e.g. "2 ranks × 8 threads · PME on GPU, non-bonded on GPU". */
export function configSummary(engine: Engine, values: HardwareConfigValues): string {
  const split = `${count(values.np, "rank")} × ${count(values.ntomp, "thread")}`
  const placement =
    engine === Engine.AMBER
      ? `${values.pickA}, ${values.pickB} Ewald`
      : `PME on ${values.pickA.toUpperCase()}, non-bonded on ${values.pickB.toUpperCase()}`
  return `${split} · ${placement}`
}
