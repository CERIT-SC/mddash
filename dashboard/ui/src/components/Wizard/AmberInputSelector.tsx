import type { FileOption } from "@/util/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import FileSelector from "@/components/FileSelector"

interface AmberInputSelectorProps {
  experimentId: string
  onPrmtopSelected: (file: FileOption | null) => void
  onInpcrdSelected: (file: FileOption | null) => void
  onMdinSelected: (file: FileOption | null) => void
}

const AmberInputSelector = (props: AmberInputSelectorProps) => {
  const { experimentId, onPrmtopSelected, onInpcrdSelected, onMdinSelected } = props

  return (
    <Card className="w-80 shrink-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">AMBER Inputs</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <FileSelector
          experimentId={experimentId}
          ext={["prmtop", "parm7"]}
          title="Topology"
          onFileSelected={onPrmtopSelected}
        />

        <FileSelector
          experimentId={experimentId}
          ext={["inpcrd", "rst7", "nc"]}
          title="Coordinates"
          onFileSelected={onInpcrdSelected}
        />

        <FileSelector
          experimentId={experimentId}
          ext={["mdin", "in"]}
          title="Run Control"
          onFileSelected={onMdinSelected}
        />
      </CardContent>
    </Card>
  )
}

export default AmberInputSelector