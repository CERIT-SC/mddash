import { useCallback, useEffect, useMemo, useState } from "react"

import {
  Alert,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Link,
  Skeleton,
  Small,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@e-infra/design-system"
import { Play, Square, Trash2, UserPlus, Users } from "lucide-react"
import { toast } from "sonner"

import { IconCardHeader } from "../components/IconCard"
import { AuthedLayout, PageBody } from "../components/Layouts"
import { HubApi, type HubUserModel } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { formatTime } from "../lib/format"
import { mount } from "../lib/mount"
import { serverStatus } from "../lib/status"

interface AdminConfig {
  apiPageLimit: number
}

export function AdminPage() {
  const cfg = getAppConfig<AdminConfig>({
    apiPageLimit: 500,
  })
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])

  const [users, setUsers] = useState<HubUserModel[] | null>(null)
  const [forbidden, setForbidden] = useState(false)
  const [newUserName, setNewUserName] = useState("")
  const [busyRow, setBusyRow] = useState<string | null>(null)

  const refresh = useCallback(() => {
    api
      .listUsers(cfg.apiPageLimit)
      .then((list) => setUsers(list))
      .catch((e: unknown) => {
        setUsers([])
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 403) {
          setForbidden(true)
        } else {
          toast.error("Could not load users.")
        }
      })
  }, [api, cfg.apiPageLimit])

  useEffect(refresh, [refresh])

  const run = (name: string, op: () => Promise<unknown>, done: string) => {
    setBusyRow(name)
    op()
      .then(() => toast.success(done))
      .catch((e: Error) => toast.error(e.message))
      .finally(() => {
        setBusyRow(null)
        refresh()
      })
  }

  const addUser = () => {
    const name = newUserName.trim()
    if (!name) return
    run(name, () => api.addUser(name), `User ${name} created.`)
    setNewUserName("")
  }

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      current="admin"
      announcement={cfg.announcement}
    >
      <PageBody>
        <Card>
          <IconCardHeader
            icon={Users}
            title="Users"
            description="Start or stop user servers, grant admin rights, add or remove users."
          />
          <CardContent className="flex flex-col gap-6">
            <div className="flex items-end gap-2">
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="new-user-name">Add user</Label>
                <Input
                  id="new-user-name"
                  placeholder="username"
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") addUser()
                  }}
                />
              </div>
              <Button onClick={addUser} disabled={!newUserName.trim()}>
                <UserPlus size={16} />
                Add
              </Button>
            </div>

            {forbidden ? (
              <Alert variant="error">You do not have permission to administer this hub.</Alert>
            ) : users === null ? (
              <div className="flex flex-col gap-2">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : users.length === 0 ? (
              <Small className="text-text-muted">No users found.</Small>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Admin</TableHead>
                      <TableHead>Server</TableHead>
                      <TableHead>Last activity</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((user) => {
                      const status = serverStatus(user.servers?.[""])
                      const serverUrl = `${cfg.baseUrl}user/${encodeURIComponent(user.name)}/`
                      const busy = busyRow === user.name
                      return (
                        <TableRow key={user.name}>
                          <TableCell className="font-medium">{user.name}</TableCell>
                          <TableCell>
                            <Switch
                              checked={user.admin}
                              disabled={busy}
                              aria-label={`Admin rights for ${user.name}`}
                              onCheckedChange={(checked) =>
                                run(
                                  user.name,
                                  () => api.editUser(user.name, { admin: checked }),
                                  `Updated ${user.name}.`
                                )
                              }
                            />
                          </TableCell>
                          <TableCell>
                            {status === "running" ? (
                              <span className="flex items-center gap-2">
                                <span className="bg-success inline-block size-2 rounded-full" />
                                Running
                                <Link href={serverUrl}>open</Link>
                              </span>
                            ) : status === "starting" ? (
                              "Starting…"
                            ) : status === "stopping" ? (
                              "Stopping…"
                            ) : (
                              <span className="text-text-muted">Stopped</span>
                            )}
                          </TableCell>
                          <TableCell className="text-text-muted text-sm">{formatTime(user.last_activity)}</TableCell>
                          <TableCell>
                            <div className="flex flex-wrap items-center gap-1">
                              {status === "running" || status === "starting" ? (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="border-error text-error hover:bg-error/10"
                                  disabled={busy}
                                  onClick={() =>
                                    run(user.name, () => api.stopServer(user.name), `Stopping ${user.name}…`)
                                  }
                                >
                                  <Square size={12} />
                                  Stop
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  disabled={busy || status === "stopping"}
                                  onClick={() =>
                                    run(user.name, () => api.startServer(user.name), `Starting ${user.name}…`)
                                  }
                                >
                                  <Play size={12} />
                                  Start
                                </Button>
                              )}
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button size="sm" variant="error" disabled={busy}>
                                    <Trash2 size={12} />
                                    Delete
                                  </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                  <AlertDialogHeader>
                                    <AlertDialogTitle>Delete user {user.name}?</AlertDialogTitle>
                                    <AlertDialogDescription>
                                      The account and any stopped servers will be removed. User data on the PVC is kept.
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <AlertDialogFooter>
                                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                                    <AlertDialogAction
                                      className="bg-error hover:bg-error/90 focus-visible:ring-error/20 text-error-foreground border-error"
                                      onClick={() =>
                                        run(user.name, () => api.deleteUser(user.name), `User ${user.name} deleted.`)
                                      }
                                    >
                                      Delete
                                    </AlertDialogAction>
                                  </AlertDialogFooter>
                                </AlertDialogContent>
                              </AlertDialog>
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </PageBody>
    </AuthedLayout>
  )
}

mount(<AdminPage />)
