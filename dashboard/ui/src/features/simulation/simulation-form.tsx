import { useEffect, useMemo } from "react"

import { toApiError } from "@/api/errors"
import {
  getGetExperimentQueryKey,
  getListSimulationsQueryKey,
  useCreateSimulation,
  useUpdateSimulation,
} from "@/api/generated/client"
import { Engine } from "@/api/generated/models"
import type { Simulation, SimulationWrite } from "@/api/generated/models"
import { ENGINE_LABELS } from "@/shared/engine"
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from "@e-infra/design-system"
import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { LoaderCircle, Lock, Save, TriangleAlert } from "lucide-react"
import { useForm, useWatch, type UseFormReturn } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { FileRoleSelect, RolePresenceBadge } from "./file-role-select"
import {
  dirname,
  DRIVER_ROLE,
  joinPath,
  ROLE_SPECS,
  rolePresence,
  roleValuesFromSimulation,
  stem,
  TRAJECTORY_EXTENSION,
} from "./simulation-roles"

// Mirrors the manifest JSON schema (dashboard/api/manifest_schemas/*).
const NAME_PATTERN = /^[A-Za-z0-9_.-]+$/
const RELPATH_PATTERN = /^[A-Za-z0-9_./-]+$/

// All roles across both engines, statically keyed; ROLE_SPECS[engine] decides
// which are rendered and submitted.
export type SimulationFormValues = {
  name: string
  extra_args: string
  run_input: string
  run_structure: string
  reference_structure: string
  trajectory: string
  topology: string
  coordinates: string
  control: string
}

function buildSchema(engine: Engine) {
  const roles = ROLE_SPECS[engine]
  return z
    .object({
      name: z.string().min(1, "Required").regex(NAME_PATTERN, "Letters, digits, dots, dashes, and underscores only"),
      extra_args: z.string(),
      run_input: z.string(),
      run_structure: z.string(),
      reference_structure: z.string(),
      trajectory: z.string(),
      topology: z.string(),
      coordinates: z.string(),
      control: z.string(),
    })
    .superRefine((values, context) => {
      for (const role of roles) {
        const value = values[role.key] ?? ""
        if (role.required && value === "") {
          context.addIssue({ code: "custom", path: [role.key], message: "Required" })
        } else if (value !== "" && role.section === "output" && !isSafeRelpath(value)) {
          context.addIssue({ code: "custom", path: [role.key], message: "Not a valid experiment-relative path" })
        }
      }
    })
}

function isSafeRelpath(path: string): boolean {
  return RELPATH_PATTERN.test(path) && !path.startsWith("/") && !path.includes("..") && !path.includes("//")
}

function defaultValues(engine: Engine, simulation?: Simulation): SimulationFormValues {
  const values: SimulationFormValues = {
    name: simulation?.name ?? "",
    extra_args: simulation?.extra_args ?? "",
    run_input: "",
    run_structure: "",
    reference_structure: "",
    trajectory: "",
    topology: "",
    coordinates: "",
    control: "",
  }
  const roleValues = simulation ? roleValuesFromSimulation(simulation) : {}
  for (const role of ROLE_SPECS[engine]) {
    values[role.key] = roleValues[role.key] ?? ""
  }
  return values
}

function writePayload(engine: Engine, values: SimulationFormValues): SimulationWrite {
  const files: Record<string, string> = {}
  for (const role of ROLE_SPECS[engine]) {
    if (values[role.key] !== "") files[role.key] = values[role.key]
  }
  return { name: values.name.trim(), files, extra_args: values.extra_args }
}

function AutoFill({
  form,
  engine,
  creating,
}: {
  form: UseFormReturn<SimulationFormValues>
  engine: Engine
  creating: boolean
}) {
  const driver = useWatch({ control: form.control, name: DRIVER_ROLE[engine] })
  useEffect(() => {
    if (!creating || driver === "" || driver === undefined) return
    const base = stem(driver)
    const dir = dirname(driver)
    const fill = (key: keyof SimulationFormValues, value: string) => {
      if (form.getValues(key) === "") form.setValue(key, value)
    }
    fill("name", base)
    fill("trajectory", joinPath(dir, `${base}.${TRAJECTORY_EXTENSION[engine]}`))
    if (engine === Engine.GMX) fill("run_structure", joinPath(dir, `${base}.gro`))
  }, [driver, creating, engine, form])
  return null
}

type SimulationFormProps = {
  experimentId: string
  engine: Engine
  /** Undefined renders the create variant. */
  simulation?: Simulation
  /** Called after a successful save so the wizard can move the URL selection. */
  onSaved?: (simulation: Simulation, created: boolean) => void
}

export function SimulationForm({ experimentId, engine, simulation, onSaved }: SimulationFormProps) {
  const queryClient = useQueryClient()
  const schema = useMemo(() => buildSchema(engine), [engine])
  const locked = simulation?.locked ?? false
  const existingPath = simulation?.simulation_path

  const form = useForm<SimulationFormValues>({
    resolver: zodResolver(schema),
    mode: "onChange",
    values: useMemo(() => defaultValues(engine, simulation), [engine, simulation]),
    // React 19: FormProvider overrides keep clean — poll refreshes adopt server state
    // only when the user hasn't diverged from it.
    resetOptions: { keepDirtyValues: true },
  })

  // A different manifest (tab switch / lock flip) restarts the form from its data.
  useEffect(() => {
    form.reset(defaultValues(engine, simulation))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingPath, locked, engine, form])

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: getListSimulationsQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
  }

  const create = useCreateSimulation({
    mutation: {
      onSuccess: (response) => {
        const created = response.status === 201 ? response.data : undefined
        toast.success(`Simulation “${created?.name ?? form.getValues("name")}” created`)
        invalidate()
        if (created) {
          form.reset(defaultValues(engine, created))
          onSaved?.(created, true)
        }
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  const update = useUpdateSimulation({
    mutation: {
      onSuccess: (response) => {
        const saved = response.status === 200 ? response.data : undefined
        toast.success(`Simulation “${saved?.name ?? ""}” saved`)
        invalidate()
        if (saved) {
          form.reset(defaultValues(engine, saved))
          onSaved?.(saved, false)
        }
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  const pending = create.isPending || update.isPending
  const editing = simulation !== undefined

  function onSubmit(values: SimulationFormValues) {
    const data = writePayload(engine, values)
    if (editing) {
      update.mutate({ experimentId, simulationPath: simulation.simulation_path, data })
    } else {
      create.mutate({ experimentId, data })
    }
  }

  const roleBadge = (key: string): boolean | null => (simulation === undefined ? null : rolePresence(simulation, key))
  const inputRoles = ROLE_SPECS[engine].filter((role) => role.section === "input")
  const outputRoles = ROLE_SPECS[engine].filter((role) => role.section === "output")
  const canSubmit = form.formState.isValid && !pending && (!editing || form.formState.isDirty)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{editing ? "Simulation" : "New simulation"}</CardTitle>
        {editing && (
          <CardAction>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{ENGINE_LABELS[engine]}</Badge>
              {locked && (
                <Badge variant="secondary">
                  <Lock aria-hidden="true" />
                  Locked
                </Badge>
              )}
              {simulation.valid ? (
                <Badge variant="outline" className="border-success-300 bg-success-50 text-success">
                  Valid
                </Badge>
              ) : (
                <Badge variant="error">Invalid</Badge>
              )}
            </div>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <AutoFill form={form} engine={engine} creating={!editing} />
            <fieldset disabled={locked || pending} className="space-y-6 disabled:opacity-90">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={editing ? undefined : "Enter name of your choice"} />
                    </FormControl>
                    <FormDescription className="text-text-muted">Identifier for this simulation setup.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <section aria-label="Input files" className="grid gap-4 md:grid-cols-2">
                <SectionHeading>Input files</SectionHeading>
                {inputRoles.map((role) => (
                  <FileRoleSelect
                    key={role.key}
                    experimentId={experimentId}
                    spec={role}
                    present={roleBadge(role.key)}
                    disabled={locked}
                    clearVanished={!editing}
                  />
                ))}
              </section>

              <section aria-label="Output paths" className="grid gap-4 md:grid-cols-2">
                <SectionHeading>Output paths</SectionHeading>
                {outputRoles.map((role) => (
                  <FormField
                    key={role.key}
                    control={form.control}
                    name={role.key}
                    render={({ field }) => {
                      const presence = roleBadge(role.key)
                      return (
                        <FormItem>
                          <div className="flex items-center gap-2">
                            <FormLabel>{role.label}</FormLabel>
                            {presence !== null && <RolePresenceBadge presence={presence} />}
                          </div>
                          <FormControl>
                            <Input
                              {...field}
                              placeholder={
                                role.key === "trajectory"
                                  ? `production/protein.${TRAJECTORY_EXTENSION[engine]}`
                                  : "production/protein.gro"
                              }
                            />
                          </FormControl>
                          <FormDescription className="text-text-muted">{role.help}</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )
                    }}
                  />
                ))}
              </section>

              <section aria-label="Runtime options" className="grid gap-4">
                <SectionHeading>Runtime options</SectionHeading>
                <FormField
                  control={form.control}
                  name="extra_args"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="sr-only">CLI flags</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder="No CLI Flags" />
                      </FormControl>
                      <FormDescription className="text-text-muted">
                        Additional {ENGINE_LABELS[engine]} CLI flags passed to mdrun.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </section>
            </fieldset>

            {editing && !simulation.valid && simulation.errors.length > 0 && (
              <Alert variant="error">
                <TriangleAlert aria-hidden="true" />
                <AlertTitle>Manifest validation failed</AlertTitle>
                <AlertDescription>
                  <ul className="list-inside list-disc">
                    {simulation.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {!locked && (
              <div className="flex justify-end">
                <Button type="submit" disabled={!canSubmit}>
                  {pending ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                  {editing ? "Save changes" : "Create simulation"}
                </Button>
              </div>
            )}
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <p className="text-text-muted col-span-full text-xs font-semibold tracking-widest uppercase">{children}</p>
}
