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

