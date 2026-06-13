#!/usr/bin/env bash
# Сборка образа внутри кластера через Kaniko (локальная машина слабая для
# тяжёлого torch-образа). Контекст заливается в PVC build-ctx через ctx-loader
# (RWO — поэтому loader удаляется перед запуском Kaniko), затем Kaniko-Job
# собирает из dir:///workspace и пушит в реестр.
#
# Usage: kbuild.sh <ctx_tar> <dockerfile> <destination> <mem_limit> [extra kaniko args...]
set -euo pipefail

CTX_TAR="$1"; DOCKERFILE="$2"; DEST="$3"; MEM="$4"; shift 4
EXTRA_ARGS=("$@")
NS=ai-message
export KUBECONFIG="${KUBECONFIG:-/root/.kube/config}"

echo ">>> [1/5] ctx-loader: заливаем контекст в PVC build-ctx"
kubectl -n "$NS" delete pod ctx-loader --ignore-not-found --wait=true >/dev/null 2>&1 || true
kubectl -n "$NS" apply -f - >/dev/null <<'YAML'
apiVersion: v1
kind: Pod
metadata: { name: ctx-loader, namespace: ai-message }
spec:
  restartPolicy: Never
  containers:
  - name: loader
    image: busybox:1.36
    command: ["sh","-c","sleep 3600"]
    volumeMounts: [{ name: ctx, mountPath: /workspace }]
  volumes:
  - name: ctx
    persistentVolumeClaim: { claimName: build-ctx }
YAML
kubectl -n "$NS" wait --for=condition=Ready pod/ctx-loader --timeout=120s

echo ">>> [2/5] чистим PVC и распаковываем контекст"
kubectl -n "$NS" exec ctx-loader -- sh -c 'rm -rf /workspace/* /workspace/.[!.]* 2>/dev/null; mkdir -p /workspace'
kubectl -n "$NS" cp "$CTX_TAR" ctx-loader:/tmp/ctx.tar
kubectl -n "$NS" exec ctx-loader -- sh -c 'tar -xf /tmp/ctx.tar -C /workspace && rm -f /tmp/ctx.tar && ls /workspace | head'
kubectl -n "$NS" delete pod ctx-loader --wait=true >/dev/null

echo ">>> [3/5] запускаем Kaniko-Job → $DEST"
JOB=kaniko-$(echo "$DEST" | sed 's#.*/##; s#:.*##')
kubectl -n "$NS" delete job "$JOB" --ignore-not-found --wait=true >/dev/null 2>&1 || true
ARGS_YAML="        - --context=dir:///workspace
        - --dockerfile=/workspace/Dockerfile
        - --destination=$DEST
        - --cleanup"
for a in "${EXTRA_ARGS[@]}"; do ARGS_YAML="$ARGS_YAML
        - $a"; done

kubectl -n "$NS" apply -f - >/dev/null <<YAML
apiVersion: batch/v1
kind: Job
metadata: { name: $JOB, namespace: $NS }
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: kaniko
        image: gcr.io/kaniko-project/executor:latest
        args:
$ARGS_YAML
        resources:
          requests: { memory: 1Gi }
          limits: { memory: $MEM }
        volumeMounts:
        - { name: ctx, mountPath: /workspace }
        - { name: docker-config, mountPath: /kaniko/.docker }
      volumes:
      - name: ctx
        persistentVolumeClaim: { claimName: build-ctx }
      - name: docker-config
        secret:
          secretName: kaniko-reg
          items: [{ key: .dockerconfigjson, path: config.json }]
YAML

echo ">>> [4/5] ждём завершения Job $JOB (поток логов)"
sleep 4
kubectl -n "$NS" wait --for=condition=Ready pod -l job-name="$JOB" --timeout=180s 2>/dev/null || true
kubectl -n "$NS" logs -f -l job-name="$JOB" --tail=-1 || true

echo ">>> [5/5] статус Job"
kubectl -n "$NS" wait --for=condition=complete job/"$JOB" --timeout=1200s && echo "BUILD OK: $DEST" || {
  echo "BUILD FAILED: $DEST"; kubectl -n "$NS" describe job/"$JOB" | tail -20; exit 1; }
kubectl -n "$NS" delete job "$JOB" --wait=false >/dev/null 2>&1 || true
