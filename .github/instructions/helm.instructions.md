---
applyTo: 'helm/**/Chart.yaml, helm/**/values.yaml, helm/**/templates/*.yaml, helm/**/templates/*.tpl'
---

# Helm Chart Best Practices

Apply these rules when creating or modifying Helm charts. All examples marked "Correct" are the expected patterns.

## Naming and Structure Rules

**Chart Names:**
- Pattern: `lowercase-with-hyphens`
- MUST: Start with letter, use only `[a-z0-9-]`
- MUST NOT: Use uppercase, underscores, dots
- Directory name MUST match chart name exactly
- Examples: `nginx-ingress`, `cert-manager`, `oauth2-proxy`

**Versioning:**
- Use SemVer 2 format (e.g., `1.2.3`)
- `version`: Chart version (increment on changes)
- `appVersion`: Application version (quoted string)
- Replace `+` with `_` in Kubernetes labels

**File Organization:**
- Templates: `*.yaml` (Kubernetes manifests), `*.tpl` (helpers)
- Naming: `resource-kind.yaml` (e.g., `app-deployment.yaml`)
- Rule: One resource per file

## YAML Formatting Rules

- Indentation: 2 spaces (never tabs)
- Template syntax: `{{ .Value }}` (spaces inside braces)
- Template names: Always namespace with chart name prefix

```yaml
# Correct template naming
{{- define "chartname.fullname" }}
{{- .Release.Name }}-{{ .Chart.Name }}
{{- end }}

# Incorrect - causes conflicts
{{- define "fullname" }}...{{- end }}
```

## Values File Requirements

**Naming Convention:**
- Pattern: `camelCase`
- Start with lowercase letter
- MUST NOT: Use hyphens, start with uppercase
- Examples: `replicaCount`, `serviceAccountName`, `enableMetrics`

**Structure:**
- Prefer flat over nested (easier to override with `--set`)
- Use maps instead of arrays when possible

```yaml
# Good - flat structure
serverHost: "example.com"
serverPort: "8080"

# Avoid - complex nesting
server:
  config:
    host: "example.com"
```

**Type Safety:**
- MUST: Quote all strings (including version numbers)
- MUST: Quote large integers to prevent scientific notation
- Booleans: No quotes needed

```yaml
# Correct
image:
  tag: "1.2.3"
  pullPolicy: "IfNotPresent"
port: "8080"
enabled: false
```

**Documentation:**
- MUST: Document every value with comment starting with parameter name

```yaml
# replicaCount is the number of pod replicas to deploy
replicaCount: 3

# serverHost is the hostname for the webserver
serverHost: "example.com"
```

## Template Validation Rules

**Input Validation:**
- Use `required` for mandatory values
- Use `default` for optional values with fallback
- Use `quote` for string interpolation
- Use `toYaml` for complex objects

```yaml
# Mandatory values
metadata:
  name: {{ required "serviceName is required" .Values.serviceName }}

# Optional with default
replicas: {{ .Values.replicaCount | default 1 }}

# Safe string handling
value: {{ .Values.dbHost | quote }}
```

**Security - Prevent Injection:**
- MUST NOT: Concatenate user input directly into commands
- MUST: Use `quote` or `toYaml` for external variables
- MUST: Validate all user-provided inputs

## Security Requirements

**Secrets:**
- MUST NOT: Hardcode secrets in values or templates
- Use `lookup` to check existing secrets
- Generate random values with `randAlphaNum`
- Add `helm.sh/resource-policy: keep` to preserve on upgrade

```yaml
{{- if not (lookup "v1" "Secret" .Release.Namespace "app-secret") }}
apiVersion: v1
kind: Secret
metadata:
  name: app-secret
  annotations:
    "helm.sh/resource-policy": "keep"
stringData:
  password: {{ randAlphaNum 32 }}
{{- end }}
```

**RBAC:**
- MUST: Use least-privilege principle
- Create dedicated ServiceAccount, Role, RoleBinding
- MUST NOT: Use `cluster-admin` unless absolutely necessary
- Limit verbs to minimum required (avoid `*`)

**Security Context (Required Defaults):**
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
```

**Sensitive Defaults:**
- MUST NOT: Provide default passwords
- Use `required` to force user input OR generate random values
- Disable optional features by default (explicit enable)

## Resource Specifications

**Always Include:**

```yaml
# Resource limits/requests
resources:
  limits:
    cpu: {{ .Values.resources.limits.cpu | default "500m" }}
    memory: {{ .Values.resources.limits.memory | default "512Mi" }}
  requests:
    cpu: {{ .Values.resources.requests.cpu | default "100m" }}
    memory: {{ .Values.resources.requests.memory | default "128Mi" }}

# Health checks
livenessProbe:
  httpGet:
    path: {{ .Values.healthCheckPath | default "/health" }}
    port: http
  initialDelaySeconds: 30
readinessProbe:
  httpGet:
    path: {{ .Values.healthCheckPath | default "/ready" }}
    port: http
  initialDelaySeconds: 5
```

## Testing and Documentation

**Required Files:**
- `Chart.yaml`: Metadata with name, version, appVersion
- `values.yaml`: All configurable parameters with comments
- `README.md`: Installation and configuration guide
- `templates/NOTES.txt`: Post-install instructions
- `templates/tests/`: Test pods with `helm.sh/hook: test` annotation

**Validation Commands:**
```bash
helm lint ./mychart                          # Validate syntax
helm template ./mychart --debug              # Render templates
helm install --dry-run --debug test ./mychart  # Simulate install
helm test <release-name>                     # Run tests
```

**Security Scanning:**
- Integrate `trivy` or `checkov` in CI/CD
- Scan for misconfigurations and vulnerabilities
- Review dependencies before each release

## Conditional Resources

Use `enabled` flags for optional components:

```yaml
# values.yaml
monitoring:
  enabled: false

# Chart.yaml dependencies
dependencies:
- name: prometheus
  condition: monitoring.enabled
  
# templates/monitoring.yaml
{{- if .Values.monitoring.enabled }}
apiVersion: v1
kind: Service
...
{{- end }}
```

## Common Mistakes to Avoid

- Using uppercase or underscores in chart/value names
- Unquoted strings in values.yaml
- Hardcoded secrets or default passwords
- Running containers as root user
- Missing resource limits
- Overly permissive RBAC (cluster-admin)
- Undocumented values
- Directly interpolating user input into commands
- Using complex nested structures when flat would work
- Missing health checks (liveness/readiness probes)
