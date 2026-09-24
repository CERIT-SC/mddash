#!/usr/bin/env bash
# MDDash interactive installer: deploys from config*.yaml to a Kubernetes cluster.
#
# Assumes images and Helm charts already exist in the configured registry
# (normally cerit.io/mddash, populated by CI); with a custom registry, push them yourself.
#
# Usage:
#   ./install.sh            # dry-run: print what would happen (default)
#   ./install.sh --execute  # apply the mutations for real
set -euo pipefail

DRY_RUN=1
case "${1:-}" in
  --execute) DRY_RUN=0 ;;
  "" ) ;;
  *) echo "usage: $0 [--execute]" >&2; exit 2 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------- helpers

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

# prompt VAR "question" [default]
prompt() {
  local var="$1" question="$2" default="${3:-}" reply
  printf '  %s%s: ' "$(cyan "$question")" "${default:+ $(dim "[$default]")}"
  read -r reply
  printf -v "$var" '%s' "${reply:-$default}"
}

# prompt_secret VAR "question": masked input, re-prompts until non-empty
prompt_secret() {
  local var="$1" question="$2" reply=""
  while [[ -z "$reply" ]]; do
    printf '  %s: ' "$(cyan "$question")"
    read -rs reply
    printf '\n'
  done
  printf -v "$var" '%s' "$reply"
}

# confirm "question" [Y|N default] -> 0=yes 1=no
confirm() {
  local question="$1" default="${2:-Y}" hint reply
  [[ "$default" == Y ]] && hint="Y/n" || hint="y/N"
  printf '  %s %s: ' "$(cyan "$question")" "$(dim "[$hint]")"
  read -r reply
  [[ "${reply:-$default}" =~ ^[Yy]$ ]]
}

# choose VAR "question" default_index option...
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
  printf '  %s: ' "$(cyan "Select") $(dim "[1-$#, default $default]")"
  read -r reply
  reply="${reply:-$default}"
  if ! [[ "$reply" =~ ^[0-9]+$ ]] || (( reply < 1 || reply > $# )); then
    die "invalid selection: $reply"
  fi
  printf -v "$var" '%s' "${!reply}"
}

# run CMD [DISPLAY]: single binding point for mutating commands; DISPLAY masks CMD in output (secrets).
run() {
  local cmd="$1" display="${2:-$1}"
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  %s %s\n' "$(yellow "[dry-run]")" "$(bold "$display")"
  else
    printf '  %s %s\n' "$(green "[run]")" "$display"
    eval "$cmd"
  fi
}

# rancher_wait DESCRIPTION TEST_COMMAND: poll (60s) until Rancher reflects a change.
# No-op in dry-run; soft-fails with a manual-fallback warning in execute mode.
rancher_wait() {
  local desc="$1" test_cmd="$2" waited=0
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  %s would wait for %s\n' "$(yellow "[dry-run]")" "$desc"
    return 0
  fi
  info "waiting for $desc..."
  until eval "$test_cmd"; do
    if (( waited >= 60 )); then
      warn "timed out waiting for $desc"
      warn "if this cluster is not Rancher-managed, remove rancherProjectId from $CONFIG;"
      warn "otherwise finish the quota setup in the Rancher UI (docs/resource-management.md)"
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 0
}

# ---------------------------------------------------------------- environment

missing=""
for tool in git kubectl helm yq gomplate make openssl python3; do
  command -v "$tool" >/dev/null 2>&1 || missing+=" $tool"
done
[[ -z "$missing" ]] || die "missing tools:$missing (all available in the dev container)"

[[ $DRY_RUN -eq 1 ]] && info "$(bold dry-run): mutating commands are printed, not executed. Apply with $(bold "./install.sh --execute")"

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
[[ "$RANCHER_PROJECT_ID" == "null" ]] && RANCHER_PROJECT_ID=""

info "deploying $(bold "$ENV"): namespace $NAMESPACE, helm package $PACKAGE, https://$HOSTNAME"
if [[ "$REGISTRY" != "cerit.io/mddash" ]]; then
  warn "custom registry $REGISTRY: images and Helm charts must already exist there; this script only deploys"
fi

# ---------------------------------------------------------------- cluster

mapfile -t contexts < <(kubectl config get-contexts -o name 2>/dev/null || true)
[[ ${#contexts[@]} -gt 0 ]] || die "no kubectl contexts configured"
current_ctx="$(kubectl config current-context 2>/dev/null || true)"
if (( ${#contexts[@]} > 2 )) || [[ -z "$current_ctx" && ${#contexts[@]} -gt 1 ]]; then
  # multiple plausible targets (or no current context to default to): make the choice explicit
  default_ctx=1
  for i in "${!contexts[@]}"; do [[ "${contexts[$i]}" == "$current_ctx" ]] && default_ctx=$((i + 1)); done
  choose KUBE_CONTEXT "Available kubeconfig contexts:" "$default_ctx" "${contexts[@]}"
else
  KUBE_CONTEXT="${current_ctx:-${contexts[0]}}"
fi
info "kubectl context: $(bold "$KUBE_CONTEXT")"
run "kubectl config use-context '$KUBE_CONTEXT'"
kubectl get --raw=/readyz >/dev/null 2>&1 || die "cluster not reachable via context $KUBE_CONTEXT"

# ---------------------------------------------------------------- image tag

if [[ "$ENV" == "dev" ]]; then
  IMAGE_TAG=dev
elif [[ "$REGISTRY" != "cerit.io/mddash" ]]; then
  # custom registry: artifacts are the operator's own, so the tag cannot be inferred from upstream releases
  prompt IMAGE_TAG "Image tag to deploy (SemVer x.y.z)"
  [[ "$IMAGE_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "tag must be strict SemVer x.y.z"
else
  # remote tags define which artifacts exist; checkout must match the tag because the
  # values template and pre_spawn_hook.py come from the local clone (hook/image version coupling)
  LATEST_TAG="$(git ls-remote --tags --refs origin 'v*' 2>/dev/null | awk -F/ '{print $NF}' | sort -V | tail -1 || true)"
  [[ "$LATEST_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "could not resolve the latest release tag from origin (check network/access to: $(git remote get-url origin 2>/dev/null || echo origin))"
  git rev-parse --verify --quiet "refs/tags/$LATEST_TAG" >/dev/null \
    || die "latest upstream release is $LATEST_TAG but your clone lacks it: git fetch --tags origin && git checkout $LATEST_TAG, then re-run"
  [[ "$(git rev-parse HEAD)" == "$(git rev-list -n1 "$LATEST_TAG")" ]] \
    || die "deploying $LATEST_TAG requires its exact checkout: git checkout $LATEST_TAG, then re-run (current HEAD: $(git rev-parse --short HEAD))"
  IMAGE_TAG="${LATEST_TAG#v}"
fi
info "image tag: $(bold "$IMAGE_TAG")"

# ---------------------------------------------------------------- namespace & quota

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
  info "the project limit must fit hub + users; full breakdown: $(bold "make resources ENV=$ENV")"

  QUOTA_JSON="{\"limit\":{\"limitsCpu\":\"$HUB_LCPU\",\"limitsMemory\":\"$HUB_LMEM\",\"requestsCpu\":\"$HUB_RCPU\",\"requestsMemory\":\"$HUB_RMEM\"}}"
  PATCH="$(PROJECT="$RANCHER_PROJECT_ID" QUOTA="$QUOTA_JSON" yq -n \
    '{"metadata": {"annotations": {"field.cattle.io/projectId": strenv(PROJECT), "field.cattle.io/resourceQuota": strenv(QUOTA)}}}')"
  printf '%s\n' "$PATCH" | sed 's/^/    /'
  PATCH_JSON="$(yq -o=json -I=0 <<<"$PATCH")"
  run "kubectl patch namespace '$NAMESPACE' --type merge -p '$PATCH_JSON'"
  # the ResourceQuota object appearing proves Rancher enrolled the namespace and synced the quota
  rancher_wait "ResourceQuota object in $NAMESPACE" \
    "kubectl get resourcequota -n '$NAMESPACE' --no-headers 2>/dev/null | grep -q ."
fi

# ---------------------------------------------------------------- cluster RBAC

RBAC_DIR="$(mktemp -d)"
trap 'rm -rf "$RBAC_DIR"' EXIT
sed "s/<NAMESPACE>/$NAMESPACE/g" helm/rbac/clusterrole.yaml > "$RBAC_DIR/clusterrole.yaml"
if [[ -n "$RANCHER_PROJECT_ID" ]]; then
  sed -e "s/<NAMESPACE>/$NAMESPACE/g" -e "s/<PROJECT_ID>/${RANCHER_PROJECT_ID##*p-}/g" \
    helm/rbac/rancher-clusterrole.yaml > "$RBAC_DIR/rancher-clusterrole.yaml"
fi

apply_rbac=true
if ! kubectl auth can-i create clusterroles >/dev/null 2>&1 \
  || ! kubectl auth can-i create clusterrolebindings >/dev/null 2>&1; then
  if ! confirm "Cluster-admin rights are needed to apply helm/rbac/. Do you have them?" N; then
    warn "ask your cluster admin to apply the following (rendered for namespace $NAMESPACE, no repo clone needed):"
    echo
    # heredoc body and EOF stay at column 0: indented '---' is not a valid YAML document separator
    printf '    %s\n' "$(bold "kubectl apply -f - <<'EOF'")"
    cat "$RBAC_DIR"/*.yaml
    printf 'EOF\n'
    echo
    confirm "Has the admin applied the RBAC?" N || die "re-run the installer once the RBAC is in place"
    apply_rbac=false
  fi
fi
if [[ "$apply_rbac" == true ]]; then
  for manifest in "$RBAC_DIR"/*.yaml; do
    run "kubectl apply -f '$manifest'"
  done
fi

# ---------------------------------------------------------------- secrets

# create_secret NAME key:label ...: prompts for values only when the secret is missing
create_secret() {
  local name="$1" args="" masked="" key label value pair
  shift
  if kubectl get secret "$name" -n "$NAMESPACE" >/dev/null 2>&1; then
    ok "secret $name exists, keeping"
    return
  fi
  for pair in "$@"; do
    key="${pair%%:*}"; label="${pair#*:}"
    prompt_secret value "$label"
    args+=" --from-literal=$key='$value'"
    masked+=" --from-literal=$key=<hidden>"
  done
  run "kubectl create secret generic '$name'$args -n '$NAMESPACE' --dry-run=client -o yaml | kubectl apply -f -" \
      "kubectl create secret generic '$name'$masked -n '$NAMESPACE' --dry-run=client -o yaml | kubectl apply -f -"
}

create_secret oidc-credentials "client_id:OIDC client ID" "client_secret:OIDC client secret"
create_secret "${PACKAGE}-s3-creds" "S3_ACCESS_KEY:S3 access key" "S3_SECRET_KEY:S3 secret key"
create_secret "${PACKAGE}-mdrepo-credentials" "client_id:MDRepo client ID" "client_secret:MDRepo client secret"
kubectl get secret tuner-auth -n "$NAMESPACE" >/dev/null 2>&1 \
  || run "kubectl create secret generic tuner-auth --from-literal=user=tuner --from-literal=password=\"\$(openssl rand -base64 32)\" -n '$NAMESPACE'"

# ---------------------------------------------------------------- deploy

run "make -C helm update ENV=$ENV"
if helm status "$PACKAGE" -n "$NAMESPACE" >/dev/null 2>&1; then
  run "make -C helm deploy ENV=$ENV IMAGE_TAG=$IMAGE_TAG"
else
  run "make -C helm install ENV=$ENV IMAGE_TAG=$IMAGE_TAG"
fi
run "make status ENV=$ENV"

echo
ok "Done: https://$HOSTNAME (ingress fallback: make -C helm port-forward ENV=$ENV)"
[[ $DRY_RUN -eq 1 ]] && info "dry-run only; apply for real with $(bold "./install.sh --execute")"
