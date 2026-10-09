#!/usr/bin/env bash
# MDDash interactive installer. Deploys from config*.yaml to a Kubernetes cluster.
#
# Assumes images and Helm charts already exist in the configured registry
# (normally cerit.io/mddash, populated by CI); with a custom registry, push them yourself.
#
# Usage:
#   ./install.sh            # deploy to a Kubernetes cluster
#   ./install.sh --dry-run  # show the actions without applying them
set -euo pipefail

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "" ) ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Helpers.

bold()   { printf '\033[1m%s\033[0m'  "$*"; }
dim()    { printf '\033[2m%s\033[0m'  "$*"; }
cyan()   { printf '\033[36m%s\033[0m' "$*"; }
green()  { printf '\033[32m%s\033[0m' "$*"; }
yellow() { printf '\033[33m%s\033[0m' "$*"; }
red()    { printf '\033[31m%s\033[0m' "$*"; }

info() { printf '  %s\n' "$*"; }
ok()   { printf '  %s %s\n' "$(green "✓")" "$*"; }
warn() { printf '  %s %s\n' "$(yellow "!")" "$*"; }
die()  { printf '%s %s\n' "$(red "error:")" "$*" >&2; exit 1; }

# Prompt for a value with an optional default.
prompt() {
  local var="$1" question="$2" default="${3:-}" reply
  printf '  %s%s: ' "$(cyan "$question")" "${default:+ $(dim "[$default]")}"
  read -r reply
  printf -v "$var" '%s' "${reply:-$default}"
}

# Read a line into the named variable without echoing it, printing '*' per character.
# Backspace removes the last character. EOF without a terminator keeps what was typed
# (piped input needs no trailing newline) and fails only when nothing was read.
read_masked() {
  local out="" ch
  while :; do
    if ! IFS= read -rsn1 ch; then
      printf -v "$1" '%s' "$out"
      [[ -n "$out" ]]
      return
    fi
    [[ -z "$ch" ]] && break
    case "$ch" in
      $'\177' | $'\b')
        [[ -n "$out" ]] && { out="${out:0:${#out}-1}"; printf '\b \b'; }
        ;;
      *)
        out+="$ch"
        printf '*'
        ;;
    esac
  done
  printf -v "$1" '%s' "$out"
}

# Prompt for a secret with masked input. Re-prompt until the input is not empty.
prompt_secret() {
  local var="$1" question="$2" secret=""
  while :; do
    printf '  %s: ' "$(cyan "$question")"
    read_masked secret || die "no input on stdin"
    printf '\n'
    [[ -n "$secret" ]] && break
    warn "empty value, try again"
  done
  printf -v "$var" '%s' "$secret"
}

# Ask a yes or no question. Return success for yes and failure for no.
confirm() {
  local question="$1" default="${2:-Y}" hint reply
  [[ "$default" == Y ]] && hint="Y/n" || hint="y/N"
  printf '  %s %s: ' "$(cyan "$question")" "$(dim "[$hint]")"
  read -r reply
  [[ "${reply:-$default}" =~ ^[Yy]$ ]]
}

# Let the user choose one option by number.
choose() {
  local var="$1" question="$2" default="$3" reply idx=1 opt
  shift 3
  printf '  %s\n' "$(cyan "$question")"
  for opt in "$@"; do
    if [[ $idx -eq $default ]]; then
      printf '    %s %s %s\n' "$(cyan "$idx)")" "$opt" "$(green "(default)")"
    else
      printf '    %s %s\n' "$(cyan "$idx)")" "$opt"
    fi
    idx=$((idx + 1))
  done
  reply=""
  until [[ "$reply" =~ ^[0-9]+$ ]] && (( reply >= 1 && reply <= $# )); do
    printf '  %s: ' "$(cyan "Select") $(dim "[1-$#, default $default]")"
    read -r reply || die "no input on stdin"
    reply="${reply:-$default}"
  done
  printf -v "$var" '%s' "${!reply}"
}

# Run a mutating command. DISPLAY masks CMD in output when it holds secrets.
run() {
  local cmd="$1" display="${2:-$1}"
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  %s %s\n' "$(yellow "[dry-run]")" "$(bold "$display")"
  else
    printf '  %s %s\n' "$(green "[run]")" "$display"
    eval "$cmd"
  fi
}

# Poll for up to 60s until Rancher reflects a change. Do nothing in dry-run.
# On timeout, warn with manual fallback instructions and continue.
rancher_wait() {
  local desc="$1" test_cmd="$2" waited=0
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  %s would wait for %s\n' "$(yellow "[dry-run]")" "$desc"
    return 0
  fi
  info "waiting for $desc..."
  until eval "$test_cmd"; do
    if (( waited >= 60 )); then
      warn "timed out waiting for $desc: finish the quota setup manually (docs/resource-management.md) or remove rancherProjectId from $CONFIG"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

# Environment.

missing=""
for tool in git kubectl helm yq gomplate make openssl python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || missing+=" $tool"
done
[[ -z "$missing" ]] || die "missing tools:$missing (all available in the dev container)"

[[ $DRY_RUN -eq 1 ]] && info "$(bold dry-run): mutating commands are printed, not executed."

mapfile -t configs < <(compgen -G config.yaml; compgen -G 'config.*.yaml' | sort)
[[ ${#configs[@]} -gt 0 ]] || die "no config*.yaml found in $REPO_ROOT"
default_cfg=1
for i in "${!configs[@]}"; do [[ "${configs[$i]}" == config.dev.yaml ]] && default_cfg=$((i + 1)); done
choose CONFIG "Config file to deploy:" "$default_cfg" "${configs[@]}"

if [[ "$CONFIG" == "config.yaml" ]]; then ENV=prod; else ENV="${CONFIG#config.}"; ENV="${ENV%.yaml}"; fi
NAMESPACE="$(yq -r '.namespace' "$CONFIG")"
PACKAGE="$(yq -r '.helm.package' "$CONFIG")"
REGISTRY="$(yq -r '.registry' "$CONFIG")"
HOSTNAME="$(yq -r '.dashboard.hostname' "$CONFIG")"
STORAGE_CLASS="$(yq -r '.storageClassName' "$CONFIG")"
RANCHER_PROJECT_ID="$(yq -r '.rancherProjectId // ""' "$CONFIG")"
S3_SEAWEEDFS="$(yq -r '.s3.seaweedfs.enabled // false' "$CONFIG")"

info "deploying $(bold "$ENV"): namespace $NAMESPACE, helm package $PACKAGE, https://$HOSTNAME"
if [[ "$REGISTRY" != "cerit.io/mddash" ]]; then
  warn "custom registry $REGISTRY: images and Helm charts must already exist there; this script only deploys"
fi

# Cluster.

mapfile -t contexts < <(kubectl config get-contexts -o name 2>/dev/null || true)
[[ ${#contexts[@]} -gt 0 ]] || die "no kubectl contexts configured"
current_ctx="$(kubectl config current-context 2>/dev/null || true)"
if (( ${#contexts[@]} > 2 )) || [[ -z "$current_ctx" && ${#contexts[@]} -gt 1 ]]; then
  # Multiple plausible targets, or no current context to default to. Make the choice explicit.
  default_ctx=1
  for i in "${!contexts[@]}"; do [[ "${contexts[$i]}" == "$current_ctx" ]] && default_ctx=$((i + 1)); done
  choose KUBE_CONTEXT "Available kubeconfig contexts:" "$default_ctx" "${contexts[@]}"
else
  KUBE_CONTEXT="${current_ctx:-${contexts[0]}}"
fi
info "kubectl context: $(bold "$KUBE_CONTEXT")"
# Fork the kubeconfig so every kubectl and helm call uses the chosen context without mutating the operator config.
TMP_WORK="$(mktemp -d)"
trap 'rm -rf "$TMP_WORK"' EXIT
kubectl config view --flatten > "$TMP_WORK/kubeconfig" 2>/dev/null || true
[[ -s "$TMP_WORK/kubeconfig" ]] || die "could not flatten kubeconfig"
export KUBECONFIG="$TMP_WORK/kubeconfig"
kubectl config use-context "$KUBE_CONTEXT" >/dev/null
kubectl get --raw=/readyz >/dev/null 2>&1 || die "cluster not reachable via context $KUBE_CONTEXT"

# Image tag.

if [[ "$ENV" == "dev" ]]; then
  IMAGE_TAG=dev
elif [[ "$REGISTRY" != "cerit.io/mddash" ]]; then
  # Custom registry. Artifacts are the operator's own, so the tag cannot come from upstream releases.
  prompt IMAGE_TAG "Image tag to deploy (SemVer x.y.z)"
  [[ "$IMAGE_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "tag must be strict SemVer x.y.z"
else
  # Remote tags define which artifacts exist. Warn only when local helm sources differ from the tag.
  LATEST_TAG="$(git ls-remote --tags --refs origin 'v*' 2>/dev/null | awk -F/ '{print $NF}' | sort -V | tail -1 || true)"
  [[ "$LATEST_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "could not resolve the latest release tag from origin (check network/access to: $(git remote get-url origin 2>/dev/null || echo origin))"
  git rev-parse --verify --quiet "refs/tags/$LATEST_TAG" >/dev/null \
    || die "latest upstream release is $LATEST_TAG but your clone lacks it: git fetch --tags origin, then re-run"
  IMAGE_TAG="${LATEST_TAG#v}"
  if ! git diff --quiet "$LATEST_TAG" -- helm/ 2>/dev/null; then
    warn "helm/ sources differ from $LATEST_TAG: release images would be paired with your checkout's chart"
    confirm "Deploy $LATEST_TAG with the local chart sources?" Y || die "re-run from a $LATEST_TAG checkout"
  fi
fi
info "image tag: $(bold "$IMAGE_TAG")"

# Namespace and quota.

if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  run "kubectl create namespace '$NAMESPACE'"
fi
kubectl get storageclass "$STORAGE_CLASS" >/dev/null 2>&1 \
  || warn "storage class $STORAGE_CLASS not found on this cluster: check storageClassName in $CONFIG"

if [[ -z "$RANCHER_PROJECT_ID" ]]; then
  info "no rancherProjectId in $CONFIG: skipping Rancher project/quota setup"
else
  existing_project="$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.metadata.annotations.field\.cattle\.io/projectId}' 2>/dev/null || true)"
  if [[ -n "$existing_project" && "$existing_project" != "$RANCHER_PROJECT_ID" ]]; then
    warn "namespace $NAMESPACE currently belongs to Rancher project $existing_project"
    confirm "Reassign it to $RANCHER_PROJECT_ID?" N || die "fix rancherProjectId in $CONFIG or reassign the namespace manually"
  fi

  budget="$(python3 scripts/resource_summary.py --json "$CONFIG")"
  HUB_RCPU="$(yq -r '.hub.requestsCpu' <<<"$budget")"
  HUB_RMEM="$(yq -r '.hub.requestsMemory' <<<"$budget")"
  HUB_LCPU="$(yq -r '.hub.limitsCpu' <<<"$budget")"
  HUB_LMEM="$(yq -r '.hub.limitsMemory' <<<"$budget")"
  USER_RCPU="$(yq -r '.resources.namespaceQuota.requestsCpu' "$CONFIG")"
  USER_RMEM="$(yq -r '.resources.namespaceQuota.requestsMemory' "$CONFIG")"
  USER_LCPU="$(yq -r '.resources.namespaceQuota.limitsCpu' "$CONFIG")"
  USER_LMEM="$(yq -r '.resources.namespaceQuota.limitsMemory' "$CONFIG")"

  info "$(bold "Rancher quota plan") (project $(bold "$RANCHER_PROJECT_ID")):"
  printf '    %-24s %s %s   %s\n' "" "$(bold "   requests")" "$(bold "    limits")" ""
  printf '    %-24s %10s %10s   %s\n' "hub namespace CPU" "$HUB_RCPU" "$HUB_LCPU" ""
  printf '    %-24s %10s %10s   %s\n' "hub namespace memory" "$HUB_RMEM" "$HUB_LMEM" "(computed worst case)"
  printf '    %-24s %10s %10s   %s\n' "user namespace CPU" "$USER_RCPU" "$USER_LCPU" ""
  printf '    %-24s %10s %10s   %s\n' "user namespace memory" "$USER_RMEM" "$USER_LMEM" "(resources.namespaceQuota, per user)"
  info "project limit must fit hub + users; full breakdown: $(bold "make resources ENV=$ENV")"

  QUOTA_JSON="{\"limit\":{\"limitsCpu\":\"$HUB_LCPU\",\"limitsMemory\":\"$HUB_LMEM\",\"requestsCpu\":\"$HUB_RCPU\",\"requestsMemory\":\"$HUB_RMEM\"}}"
  PATCH="$(PROJECT="$RANCHER_PROJECT_ID" QUOTA="$QUOTA_JSON" yq -n \
    '{"metadata": {"annotations": {"field.cattle.io/projectId": strenv(PROJECT), "field.cattle.io/resourceQuota": strenv(QUOTA)}}}')"
  printf '%s\n' "$PATCH" | sed 's/^/    /'
  PATCH_JSON="$(yq -o=json -I=0 <<<"$PATCH")"
  run "kubectl patch namespace '$NAMESPACE' --type merge -p '$PATCH_JSON'"
  # The ResourceQuota object appearing proves Rancher enrolled the namespace and synced the quota.
  rancher_wait "ResourceQuota object in $NAMESPACE" \
    "kubectl get resourcequota -n '$NAMESPACE' --no-headers 2>/dev/null | grep -q ."
fi

# Hub RBAC comes from the Rancher role template (helm/rbac/roletemplate.yaml) bound to
# system:serviceaccounts:$NAMESPACE in the project; user namespaces inherit the binding.

print_role_template() {
  while IFS= read -r line; do printf '    %s\n' "$(cyan "$line")"; done < helm/rbac/roletemplate.yaml
}

# Call the Rancher v3 API; print the response body, warn with curl's error text on failure.
rancher_api() {
  local method="$1" path="$2" body="${3:-}" curl_args=(-fsS -X "$method" -H "Authorization: Bearer $KCFG_TOKEN") out
  [[ -n "$body" ]] && curl_args+=(-H "Content-Type: application/json" -d "$body")
  if ! out="$(curl "${curl_args[@]}" "$RANCHER_API$path" 2>&1)"; then
    warn "Rancher API $method $path: $out"
    return 1
  fi
  printf '%s' "$out"
}

# Canonicalize a rules array so ordering never registers as drift.
normalize_rules() {
  yq -o=json -I=0 'map({"a": (.apiGroups | sort), "r": (.resources | sort), "v": (.verbs | sort)}) | sort_by(.a[0], .r[0])'
}

if ! kubectl get rolebindings -n "$NAMESPACE" -o json 2>/dev/null \
     | grep -q "\"system:serviceaccounts:$NAMESPACE\""; then
  warn "no project binding grants the hub service account a role template in $NAMESPACE"
  rbac_done=false
  RANCHER_API=""
  if [[ -n "$RANCHER_PROJECT_ID" && $DRY_RUN -eq 0 ]]; then
    KCFG_SERVER="$(kubectl config view --minify --raw -o jsonpath='{.clusters[0].cluster.server}')"
    KCFG_TOKEN="$(kubectl config view --minify --raw -o jsonpath='{.users[0].user.token}')"
    RANCHER_API="${KCFG_SERVER%%/k8s/clusters/*}/v3"
    # Direct (non-proxied) kubeconfigs have no /k8s/clusters suffix and no Rancher rights.
    if [[ "$RANCHER_API" == "$KCFG_SERVER/v3" || -z "$KCFG_TOKEN" ]]; then
      warn "kubeconfig is not Rancher-proxied; skipping Rancher API"
      RANCHER_API=""
    fi
  fi
  if [[ -n "$RANCHER_API" ]]; then
    TEMPLATE_ID="$(yq -r '.metadata.name' helm/rbac/roletemplate.yaml)"
    template_body="$(yq -o=json -I=0 '{"name": .metadata.name, "description": .description, "context": .context, "rules": .rules}' helm/rbac/roletemplate.yaml)"
    prtb_body="$(PROJECT="$RANCHER_PROJECT_ID" TEMPLATE="$TEMPLATE_ID" GROUP="system:serviceaccounts:$NAMESPACE" NAME="$NAMESPACE-sa" \
      yq -n -o=json -I=0 '{"name": strenv(NAME), "roleTemplateId": strenv(TEMPLATE), "projectId": strenv(PROJECT), "groupPrincipalId": strenv(GROUP)}')"
    template_ready=false
    if live="$(curl -fsS -H "Authorization: Bearer $KCFG_TOKEN" "$RANCHER_API/roletemplates/$TEMPLATE_ID" 2>/dev/null)"; then
      # An existing template may predate the repo file; rules drift leaves the hub SA
      # without permissions the per-spawn Roles grant.
      if [[ "$(printf '%s' "$live" | yq -o=json -I=0 '.rules' | normalize_rules)" == "$(printf '%s' "$template_body" | yq -o=json -I=0 '.rules' | normalize_rules)" ]]; then
        template_ready=true
      elif rancher_api PUT "/roletemplates/$TEMPLATE_ID" "$template_body" >/dev/null; then
        ok "updated role template $TEMPLATE_ID to match helm/rbac/roletemplate.yaml"
        template_ready=true
      fi
    elif rancher_api POST "/roletemplates" "$template_body" >/dev/null; then
      ok "created role template $TEMPLATE_ID"
      template_ready=true
    fi
    if [[ "$template_ready" == true ]] && rancher_api POST "/projectroletemplatebindings" "$prtb_body" >/dev/null; then
      rbac_done=true
      ok "bound system:serviceaccounts:$NAMESPACE to role template $TEMPLATE_ID in project $RANCHER_PROJECT_ID"
      rancher_wait "role-template binding in $NAMESPACE" \
        "kubectl get rolebindings -n '$NAMESPACE' -o json 2>/dev/null | grep -q '\"system:serviceaccounts:$NAMESPACE\"'"
    fi
  fi
  if [[ "$rbac_done" == false ]]; then
    info "ask a Rancher admin to create the role template once on the management cluster:"
    echo
    print_role_template
    echo
    info "and bind it in project $(bold "${RANCHER_PROJECT_ID:-<project>}") to the group $(bold "system:serviceaccounts:$NAMESPACE")"
    confirm "Is the role template in place?" N || die "re-run the installer once the binding exists"
  fi
else
  ok "hub role-template binding in place"
fi

# Secrets.

# Create a secret. Prompt for values only when the secret is missing and not in dry-run.
create_secret() {
  local name="$1" args="" masked="" key label value pair
  shift
  if kubectl get secret "$name" -n "$NAMESPACE" >/dev/null 2>&1; then
    ok "secret $name exists, keeping"
    return
  fi
  for pair in "$@"; do
    key="${pair%%:*}"; label="${pair#*:}"
    masked+=" --from-literal=$key=<hidden>"
    [[ $DRY_RUN -eq 1 ]] && continue
    prompt_secret value "$label"
    args+=" --from-literal=$key=$(printf '%q' "$value")"
  done
  run "kubectl create secret generic '$name'$args -n '$NAMESPACE' --dry-run=client -o yaml | kubectl apply -f -" \
      "kubectl create secret generic '$name'$masked -n '$NAMESPACE' --dry-run=client -o yaml | kubectl apply -f -"
}

create_secret oidc-credentials "client_id:OIDC client ID" "client_secret:OIDC client secret"
if [[ "$S3_SEAWEEDFS" == "true" ]]; then
  # Bundled store. Generate the shared identity instead of prompting for it.
  if kubectl get secret "${PACKAGE}-s3-creds" -n "$NAMESPACE" >/dev/null 2>&1; then
    ok "secret ${PACKAGE}-s3-creds exists, keeping"
  else
    s3_access_key="$(openssl rand -hex 20)"
    s3_secret_key="$(openssl rand -hex 40)"
    run "kubectl create secret generic '${PACKAGE}-s3-creds' --from-literal=S3_ACCESS_KEY=$(printf '%q' "$s3_access_key") --from-literal=S3_SECRET_KEY=$(printf '%q' "$s3_secret_key") -n '$NAMESPACE' --dry-run=client -o yaml | kubectl apply -f -" \
        "kubectl create secret generic '${PACKAGE}-s3-creds' --from-literal=S3_ACCESS_KEY=<hidden> --from-literal=S3_SECRET_KEY=<hidden> -n '$NAMESPACE' --dry-run=client -o yaml | kubectl apply -f -"
  fi
else
  create_secret "${PACKAGE}-s3-creds" "S3_ACCESS_KEY:S3 access key" "S3_SECRET_KEY:S3 secret key"
fi
create_secret "${PACKAGE}-mdrepo-credentials" "client_id:MDRepo client ID" "client_secret:MDRepo client secret"
if kubectl get secret tuner-auth -n "$NAMESPACE" >/dev/null 2>&1; then
  ok "secret tuner-auth exists, keeping"
else
  run "kubectl create secret generic tuner-auth --from-literal=user=tuner --from-literal=password=\"\$(openssl rand -base64 32)\" -n '$NAMESPACE'"
fi

# Deploy.

# helm upgrade --install covers both first install and updates.
run "make -C helm update ENV=$ENV"
run "make -C helm deploy ENV=$ENV IMAGE_TAG=$IMAGE_TAG"
run "make status ENV=$ENV"
if [[ $DRY_RUN -eq 0 ]]; then
  info "waiting for https://$HOSTNAME/hub/health..."
  curl -sf --retry 18 --retry-delay 10 --retry-all-errors --max-time 10 "https://$HOSTNAME/hub/health" >/dev/null \
    || die "hub health check failed (inspect: make logs ENV=$ENV)"
fi

echo
ok "Done: https://$HOSTNAME (ingress fallback: make -C helm port-forward ENV=$ENV)"
if [[ $DRY_RUN -eq 1 ]]; then
  info "dry-run only; re-run without --dry-run to apply"
fi
