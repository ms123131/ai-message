# Развёртывание ai-message в Kubernetes (Cloud.ru Managed K8s)

Манифесты для деплоя стека в namespace `ai-message`. Рассчитаны на кластер
Cloud.ru Evolution Managed Kubernetes с установленными ingress-nginx и
cert-manager (ClusterIssuer `letsencrypt-prod`) и StorageClass `cloudru-ssd`.

## Состав

| Файл | Объект | Назначение |
|---|---|---|
| `00-namespace.yaml` | Namespace | `ai-message` |
| `01-config.yaml` | ConfigMap | несекретная конфигурация (env) |
| `02-secret.example.yaml` | Secret (шаблон) | плейсхолдеры, коммитится в git |
| `02-secret.yaml` | Secret (реальный) | **в .gitignore**, не коммитить |
| `10-postgres.yaml` | PVC+Deployment+Service | Postgres 16 + pgvector |
| `11-redis.yaml` | PVC+Deployment+Service | Redis (очередь arq) |
| `20-api.yaml` | Deployment+Service | FastAPI + init-миграции |
| `21-worker.yaml` | Deployment | arq-воркер |
| `30-web.yaml` | ConfigMap+Deployment+Service | nginx (SPA + прокси) |
| `40-ingress.yaml` | Ingress | внешний вход + TLS |

## Предварительные требования

1. **Домен.** A-запись `app.77ais.ru` → `37.44.197.28` (LB ingress-nginx).
   Проверка: `dig +short app.77ais.ru` должен вернуть `37.44.197.28`.
2. **Container Registry.** Образы `api` (~3 ГБ, с torch) и `web` нужно собрать
   и запушить в реестр, доступный кластеру (Cloud.ru Artifact Registry).
   Поды тянут образ только из реестра — `:local` из compose в k8s не годится.

## 1. Собрать и запушить образы

```bash
# Подставьте адрес вашего реестра Cloud.ru Artifact Registry:
export REGISTRY=<registry-host>/<project>     # напр. cr.cloud.ru/ai-message

cd /home/project/ai-message

# api (общий образ для api/worker/migrate)
docker build -t $REGISTRY/ai-message-api:latest ./apps/api
# web (контекст — корень репо, см. apps/web/Dockerfile)
docker build -t $REGISTRY/ai-message-web:latest -f apps/web/Dockerfile .

docker push $REGISTRY/ai-message-api:latest
docker push $REGISTRY/ai-message-web:latest
```

Затем подставьте реестр в манифесты (плейсхолдер `__REGISTRY__`):

```bash
cd infra/k8s
sed -i "s#__REGISTRY__#$REGISTRY#g" 20-api.yaml 21-worker.yaml 30-web.yaml
```

## 2. Секрет доступа к реестру (imagePullSecret)

```bash
kubectl -n ai-message create secret docker-registry registry-cred \
  --docker-server=<registry-host> \
  --docker-username=<user> \
  --docker-password=<token>
```

(namespace создаётся в шаге 3; либо примените `00-namespace.yaml` заранее.)

## 3. Применить манифесты

```bash
cd infra/k8s
kubectl apply -f 00-namespace.yaml
kubectl apply -f 02-secret.yaml          # реальный секрет (не из *.example)
kubectl apply -f 01-config.yaml
kubectl apply -f 10-postgres.yaml -f 11-redis.yaml
kubectl apply -f 20-api.yaml -f 21-worker.yaml
kubectl apply -f 30-web.yaml -f 40-ingress.yaml
```

Порядок строгий не обязателен (init-контейнеры ждут зависимости сами),
но секрет/конфиг должны существовать до подов.

## 4. Проверка

```bash
kubectl -n ai-message get pods -w
# дождитесь api Running (холодный старт грузит torch — до ~2-3 мин)

kubectl -n ai-message get certificate          # app-77ais-tls → Ready=True
curl -sI https://app.77ais.ru/api/v1/health     # 200 OK
```

## Примечания

- **Миграции** выполняет init-контейнер `migrate` в Deployment `api`
  (`alembic upgrade head`). api всегда 1 реплика → без гонки и без
  отдельного Job/RBAC. worker ждёт готовности api.
- **Данные** (postgres, redis) — на CSI-томах `cloudru-ssd`, независимых от
  диска ноды; переживают пересоздание подов и ноды.
- **Bitrix24:** после деплоя webhook/install-URL приложения — на
  `https://app.77ais.ru` (`WEBHOOK_BASE_URL` в `01-config.yaml`).
- **Ротация секретов:** правьте `02-secret.yaml`, `kubectl apply`, затем
  `kubectl -n ai-message rollout restart deploy/api deploy/worker`.

## 5. CI/CD (автодеплой на merge в main)

Workflow `.github/workflows/deploy.yml` на каждый push в `main` (и по кнопке
`workflow_dispatch`) собирает образы api и web на GitHub-hosted runner через
buildx, пушит их в реестр с тегами `:<sha>` и `:latest`, затем
`kubectl set image` + `rollout status` по deployments `api`/`worker`/`web`.
Деплой идёт по тегу `:<sha>` — иммутабельно и откатываемо.

> Ручная сборка через Kaniko в кластере (`infra/scripts/kbuild.sh`) остаётся как
> fallback на случай недоступности GitHub Actions или нужды собрать с локального
> контекста.

**Секреты репозитория** (GitHub → Settings → Secrets and variables → Actions):

| Секрет | Что это | Как получить |
|---|---|---|
| `REGISTRY_USERNAME` | логин сервис-аккаунта Cloud.ru с правом push в реестр | key_id сервис-аккаунта (тот, чьим ключом создан `kaniko-reg`) |
| `REGISTRY_PASSWORD` | секрет этого ключа | секрет сервис-аккаунта |
| `KUBECONFIG_B64` | kubeconfig кластера в base64 | `base64 -w0 ~/.kube/config` |

Логин/пароль реестра можно сверить с уже рабочим `.dockerconfigjson`:

```bash
kubectl -n ai-message get secret kaniko-reg \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq .
```

> ⚠️ `KUBECONFIG_B64` даёт CI полный доступ к кластеру — храните только как
> GitHub Secret, не коммитьте. Для прод-контура позже стоит выпустить
> отдельный ServiceAccount с RBAC, ограниченным namespace `ai-message`
> (см. `docs/planApp.md`, трек D — D2/D10).
