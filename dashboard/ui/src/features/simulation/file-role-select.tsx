import { useEffect } from "react"

import { useListExperimentFiles } from "@/api/generated/client"
import type { FileInfo } from "@/api/generated/models"
import { formatBytes } from "@/shared/format"
import {
  Badge,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@e-infra/design-system"
import { useFormContext, useWatch } from "react-hook-form"

import type { RoleSpec } from "./simulation-roles"

// Radix Select items can't be empty strings; the "None" sentinel maps back to "".
const SELECT_NONE = "__none__"

export function RolePresenceBadge({ presence }: { presence: boolean }) {
  return (
    <Badge variant={presence ? "outline" : "error"} className={presence ? "border-success text-success" : undefined}>
      {presence ? "present" : "missing"}
    </Badge>
  )
}

function FileLabel({ file }: { file: FileInfo }) {
  const index = file.path.lastIndexOf("/")
  const dir = index === -1 ? null : file.path.slice(0, index)
  return (
    <span className="flex min-w-0 flex-col overflow-hidden">
      {dir !== null && <span className="text-text-muted truncate text-xs">{dir}/</span>}
      <span className={dir !== null ? "truncate pl-2" : "truncate"}>
        {file.name} ({formatBytes(file.size)})
      </span>
    </span>
  )
}

type FileRoleSelectProps = {
  experimentId: string
  spec: RoleSpec
  /** Presence of the selected file per the manifest's server-side check. */
  present?: boolean | null
  disabled?: boolean
  /** Create clears a vanished pick; edit keeps manifest data, showing it as
      "(missing)" so a save re-validates server-side instead of silently dropping it. */
  clearVanished: boolean
}

export function FileRoleSelect({ experimentId, spec, present, disabled, clearVanished }: FileRoleSelectProps) {
  const { control, setValue } = useFormContext()
  const filesQuery = useListExperimentFiles(experimentId, { ext: spec.ext ?? undefined }, { query: { retry: false } })
  const files = filesQuery.data?.status === 200 ? filesQuery.data.data : undefined

  const watched: unknown = useWatch({ control, name: spec.key })
  const value = typeof watched === "string" ? watched : ""
  const found = files?.some((file) => file.path === value) ?? false
  const empty = files !== undefined && files.length === 0

  useEffect(() => {
    if (clearVanished && files !== undefined && value !== "" && !found) {
      setValue(spec.key, "", { shouldValidate: true })
    }
  }, [clearVanished, files, found, value, setValue, spec.key])

  return (
    <FormField
      control={control}
      name={spec.key}
      render={({ field }) => (
        <FormItem>
          <div className="flex items-center gap-2">
            <FormLabel>{spec.label}</FormLabel>
            {present !== undefined && present !== null && <RolePresenceBadge presence={present} />}
          </div>
          <Select
            value={value}
            onValueChange={(next) => field.onChange(next === SELECT_NONE ? "" : next)}
            disabled={disabled || empty}
          >
            <FormControl>
              <SelectTrigger
                aria-label={spec.label}
                className="bg-background dark:bg-background h-auto w-full overflow-hidden text-left *:data-[slot=select-value]:line-clamp-none *:data-[slot=select-value]:min-w-0 *:data-[slot=select-value]:items-start! *:data-[slot=select-value]:overflow-hidden"
              >
                <SelectValue placeholder={empty ? "No files available yet" : "Select a file"} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              <SelectItem value={SELECT_NONE}>
                <em>None</em>
              </SelectItem>
              {files?.map((file) => (
                <SelectItem key={file.path} value={file.path}>
                  <FileLabel file={file} />
                </SelectItem>
              ))}
              {!clearVanished && files !== undefined && value !== "" && !found && (
                <SelectItem value={value}>
                  <em className="text-text-muted truncate">{value} (missing)</em>
                </SelectItem>
              )}
            </SelectContent>
          </Select>
          <FormDescription className="text-text-muted">{spec.help}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}
