# Kubernetes

Runs the single KubeCompass container against Elastic Cloud (data, search, Agent Builder and
Workflows stay in Elastic). Tested with [kind](https://kind.sigs.k8s.io/).

```bash
docker build -f deployment/docker/app.Dockerfile -t kubecompass-app .
kind create cluster --name kubecompass && kind load docker-image kubecompass-app --name kubecompass

kubectl create namespace kubecompass
kubectl -n kubecompass create secret generic kubecompass-secrets \
  --from-literal=KUBECOMPASS_ES_URL=... --from-literal=KUBECOMPASS_ES_API_KEY=... \
  --from-literal=OPENAI_API_KEY=... \n  --from-literal=KUBECOMPASS_IDENTITY_SECRET="$(openssl rand -hex 32)"   # keep stable
# Optional Google Calendar: also add KUBECOMPASS_GOOGLE_CLIENT_ID, KUBECOMPASS_GOOGLE_CLIENT_SECRET
# and KUBECOMPASS_PUBLIC_BASE_URL (docs/GOOGLE_CALENDAR.md)
kubectl apply -k deployment/kubernetes
kubectl -n kubecompass port-forward svc/kubecompass 7860:80   # http://localhost:7860
```
Use the least-privilege Elastic key (see `docs/DEPLOYMENT.md`). Non-secret settings are in
`configmap.yaml`.
