import { useEffect, useMemo } from "react"

import type {
  AmberJobRequest,
  GromacsJobRequest,
  GromacsJobRequestNb,
  GromacsJobRequestPme,
} from "@/api/generated/models"
import { Engine } from "@/api/generated/models"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@e-infra/design-system"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { z } from "zod"

const stepsField = z.coerce.number().int("Enter a whole number").min(1, "Enter at least 1")

// pickA/pickB stay engine-neutral (PME/binary and NB/Ewald); the labels and
// options in selectFields carry the engine semantics.
const hardwareConfigSchema = z.object({
  pickA: z.string().min(1, "Required"),
  pickB: z.string().min(1, "Required"),
  np: stepsField,
  ntomp: stepsField,
})

type HardwareConfigInput = z.input<typeof hardwareConfigSchema>
/** What the form produces; becomes the run request body via toJobRequest. */
export type HardwareConfigValues = z.output<typeof hardwareConfigSchema>

type SelectFieldMeta = {
  label: string
  description: string
  placeholder: string
  options: { value: string; label: string }[]
}

function selectFields(engine: Engine): [SelectFieldMeta, SelectFieldMeta] {
  if (engine === Engine.AMBER) {
    return [
      {
        label: "Binary",
        description: "Choose the AMBER executable: pmemd.cuda runs on a single GPU, pmemd.MPI scales across CPU cores.",
        placeholder: "Select binary",
        options: [
          { value: "pmemd.cuda", label: "pmemd.cuda (GPU)" },
          { value: "pmemd.MPI", label: "pmemd.MPI (CPU)" },
        ],
      },
      {
        label: "Ewald preset",
        description: "Ewald summation preset applied to the simulation settings; optimized favors GPU speed.",
        placeholder: "Select preset",
        options: [
          { value: "default", label: "Default" },
          { value: "optimized", label: "Optimized" },
        ],
      },
    ]
  }
  return [
    {
      label: "PME (Particle Mesh Ewald)",
      description: "Choose whether long-range electrostatics are calculated on the CPU or GPU.",
      placeholder: "Select hardware",
      options: [
        { value: "cpu", label: "CPU" },
        { value: "gpu", label: "GPU" },
      ],
    },
    {
      label: "NB (Non-bonded interactions)",
      description: "Choose whether short-range non-bonded interactions are calculated on the CPU or GPU.",
      placeholder: "Select hardware",
      options: [
        { value: "cpu", label: "CPU" },
        { value: "gpu", label: "GPU" },
      ],
    },
  ]
}

type HardwareConfigFormProps = {
  engine: Engine
  initial?: Partial<HardwareConfigInput>
  /** Lets an outside button submit this form via the native form attribute. */
  formId?: string
  onSubmit?: (values: HardwareConfigValues) => void
  onValidityChange: (valid: boolean) => void
}

// Validity mirrors to the parent for the Run gate. Remount via `key` to
// re-seed `initial`; the form never tracks it live, so mid-edit users aren't yanked back.
export function HardwareConfigForm({ engine, initial, formId, onSubmit, onValidityChange }: HardwareConfigFormProps) {
  const [fieldA, fieldB] = useMemo(() => selectFields(engine), [engine])
  const form = useForm<HardwareConfigInput, unknown, HardwareConfigValues>({
    resolver: zodResolver(hardwareConfigSchema),
    mode: "onChange",
    defaultValues: { pickA: "", pickB: "", np: "", ntomp: "", ...initial },
  })

  const isValid = form.formState.isValid
  useEffect(() => onValidityChange(isValid), [isValid, onValidityChange])

  return (
    <section aria-label="Hardware configuration" className="space-y-5">
      <Form {...form}>
        <form
          id={formId}
          onSubmit={(event) => {
            if (onSubmit !== undefined) void form.handleSubmit(onSubmit)(event)
          }}
          className="grid gap-4 md:grid-cols-2 md:gap-6"
        >
          {(
            [
              ["pickA", fieldA],
              ["pickB", fieldB],
            ] as const
          ).map(([name, meta]) => (
            <FormField
              key={name}
              control={form.control}
              name={name}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{meta.label}</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={meta.placeholder} />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {meta.options.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>{meta.description}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
          <FormField
            control={form.control}
            name="np"
            render={({ field }) => (
              <FormItem>
                <FormLabel>MPI Processes (MPI ranks)</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={1}
                    placeholder="Enter number of ranks"
                    {...field}
                    value={String(field.value)}
                  />
                </FormControl>
                <FormDescription>Set the number of parallel MPI ranks used by the simulation.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="ntomp"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Threads</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={1}
                    placeholder="Enter number of threads"
                    {...field}
                    value={String(field.value)}
                  />
                </FormControl>
                <FormDescription>Set the number of CPU threads used by each MPI rank.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </form>
      </Form>
    </section>
  )
}

// Maps to the run request body: pickA = pme/binary, pickB = nb/ewald. The
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
