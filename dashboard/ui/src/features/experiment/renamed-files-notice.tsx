import { Alert, AlertDescription, AlertTitle } from "@e-infra/design-system"

/** Dataset entries the import renamed because the notebooks already used the name. */
export function RenamedFilesNotice({ paths }: { paths: string[] }) {
  const count = paths.length
  return (
    <Alert>
      <AlertTitle>{count === 1 ? "1 dataset file was renamed" : `${count} dataset files were renamed`}</AlertTitle>
      <AlertDescription>
        <p>The notebooks already used these names, so the dataset copies were saved alongside them.</p>
        <ul className="mt-1 list-disc pl-5 font-mono text-xs">
          {paths.map((path) => (
            <li key={path}>{path}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  )
}
