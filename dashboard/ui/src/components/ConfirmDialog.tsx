import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

interface ConfirmDialogProps {
  open: boolean
  setOpen: (open: boolean) => void
  onConfirm?: () => void | Promise<void>
  onCancel?: () => void | Promise<void>
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  confirmColor?: "primary" | "destructive" | "warning"
}

const ConfirmDialog = (props: ConfirmDialogProps) => {
  const {
    open,
    setOpen,
    onConfirm,
    onCancel,
    title = "Confirm Action",
    message = "Are you sure you want to proceed? This action cannot be undone.",
    confirmText = "Confirm",
    cancelText = "Cancel",
    confirmColor = "destructive",
  } = props

  const handleConfirm = async () => {
    try {
      await onConfirm?.()
    } catch {
      // caller's onError handler (e.g. mutation toast) already surfaces the error
    }
    setOpen(false)
  }

  const handleCancel = async () => {
    try {
      await onCancel?.()
    } catch {
      // caller's onError handler already surfaces the error
    }
    setOpen(false)
  }

  const confirmVariant = confirmColor === "destructive" ? "destructive" : "default"
  const confirmClass = confirmColor === "warning" ? "bg-yellow-500 text-white hover:bg-yellow-600" : undefined

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{message}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel}>{cancelText}</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} variant={confirmVariant} className={confirmClass}>
            {confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default ConfirmDialog
