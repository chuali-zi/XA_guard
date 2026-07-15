{{/* Expand the chart name. */}}
{{- define "xa-guard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a release-scoped name. */}}
{{- define "xa-guard.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "xa-guard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "xa-guard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "xa-guard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "xa-guard.labels" -}}
helm.sh/chart: {{ include "xa-guard.chart" . }}
{{ include "xa-guard.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{- define "xa-guard.componentSelectorLabels" -}}
{{ include "xa-guard.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "xa-guard.componentLabels" -}}
{{ include "xa-guard.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "xa-guard.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "xa-guard.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "xa-guard.image" -}}
{{- $root := .root -}}
{{- $image := .image -}}
{{- if $image.digest -}}
{{- printf "%s@%s" $image.repository $image.digest -}}
{{- else -}}
{{- printf "%s:%s" $image.repository (default $root.Chart.AppVersion $image.tag) -}}
{{- end -}}
{{- end }}

{{- define "xa-guard.componentName" -}}
{{- printf "%s-%s" (include "xa-guard.fullname" .root) .component | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/* Required/preferred anti-affinity for HA components. */}}
{{- define "xa-guard.podAntiAffinity" -}}
{{- if .scheduling.podAntiAffinity.enabled }}
podAntiAffinity:
  {{- if .scheduling.podAntiAffinity.required }}
  requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          {{- include "xa-guard.componentSelectorLabels" (dict "root" .root "component" .component) | nindent 10 }}
      topologyKey: {{ .scheduling.podAntiAffinity.topologyKey | quote }}
  {{- else }}
  preferredDuringSchedulingIgnoredDuringExecution:
    - weight: {{ .scheduling.podAntiAffinity.weight }}
      podAffinityTerm:
        labelSelector:
          matchLabels:
            {{- include "xa-guard.componentSelectorLabels" (dict "root" .root "component" .component) | nindent 12 }}
        topologyKey: {{ .scheduling.podAntiAffinity.topologyKey | quote }}
  {{- end }}
{{- end }}
{{- end }}

{{/* Required topology spreading for HA components. */}}
{{- define "xa-guard.topologySpreadConstraints" -}}
{{- if .scheduling.topologySpread.enabled }}
- maxSkew: {{ .scheduling.topologySpread.maxSkew }}
  topologyKey: {{ .scheduling.topologySpread.topologyKey | quote }}
  whenUnsatisfiable: {{ .scheduling.topologySpread.whenUnsatisfiable }}
  {{- with .scheduling.topologySpread.minDomains }}
  minDomains: {{ . }}
  {{- end }}
  labelSelector:
    matchLabels:
      {{- include "xa-guard.componentSelectorLabels" (dict "root" .root "component" .component) | nindent 6 }}
{{- end }}
{{- end }}

{{/* Mutually exclusive local and HTTP key-provider environment. */}}
{{- define "xa-guard.keyProviderEnv" -}}
{{- $provider := required "global.kms.provider must be local or http" .Values.global.kms.provider -}}
- name: XA_GUARD_KEY_PROVIDER
  value: {{ $provider | quote }}
{{- if eq $provider "local" }}
- name: XA_GUARD_KEK_KEYRING
  valueFrom:
    secretKeyRef:
      name: {{ required "global.externalSecrets.runtime is required for local key provider" .Values.global.externalSecrets.runtime }}
      key: {{ required "global.kms.keyringSecretKey is required for local key provider" .Values.global.kms.keyringSecretKey }}
{{- else if eq $provider "http" }}
- name: XA_GUARD_KEY_PROVIDER_URL
  value: {{ required "global.kms.endpoint is required for http key provider" .Values.global.kms.endpoint | quote }}
- name: XA_GUARD_KEY_PROVIDER_AUTH_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ required "global.externalSecrets.keyProvider is required for http key provider" .Values.global.externalSecrets.keyProvider }}
      key: {{ required "global.kms.authTokenSecretKey is required for http key provider" .Values.global.kms.authTokenSecretKey }}
{{- if .Values.global.kms.caSecretName }}
- name: XA_GUARD_KEY_PROVIDER_CA_FILE
  value: /var/run/xa-guard/key-provider-ca/{{ .Values.global.kms.caSecretKey }}
{{- end }}
{{- if and .Values.referenceInfra.enabled .Values.global.kms.referenceHttpHosts }}
- name: XA_GUARD_KEY_PROVIDER_REFERENCE_HTTP_HOSTS
  value: {{ .Values.global.kms.referenceHttpHosts | quote }}
{{- end }}
{{- else }}
{{- fail "global.kms.provider must be one of: local, http" }}
{{- end }}
{{- end }}
