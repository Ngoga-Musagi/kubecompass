# Kubernetes

Runs the single KubeCompass container against Elastic Cloud (data, search, Agent Builder and
Workflows stay in Elastic). Tested with [kind](https://kind.sigs.k8s.io/).

```bash
docker build -f deployment/docker/app.Dockerfile -t kubecompass-app .
kind create cluster --name kubecompass && kind load docker-image kubecompass-app --name kubecompass

kubectl create namespace kubecompass
kubectl -n kubecompass create secret generic kubecompass-secrets \
  --from-literal=KUBECOMPASS_ES_URL=... --from-literal=KUBECOMPASS_ES_API_KEY=... \
  --from-literal=OPENAI_API_KEY=...          # or --from-env-file with a clean KEY=VALUE file
kubectl apply -k deployment/kubernetes
kubectl -n kubecompass port-forward svc/kubecompass 7860:80   # http://localhost:7860
```
Use the least-privilege Elastic key (see `docs/DEPLOYMENT.md`). Non-secret settings are in
`configmap.yaml`.
