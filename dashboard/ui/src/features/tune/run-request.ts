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
