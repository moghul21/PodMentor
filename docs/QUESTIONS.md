# 10 real questions my user will ask

Questions are written the way an SRE trainee preparing for Kubernetes on-call or CKA interviews would type them. At least 3 need more than one source file to answer, and question 10 cannot be answered from the Kubernetes source code alone.

| # | Question | Where the answer is (document, page / file) | Needs more than one page? |
|---|---|---|---|
| 1 | Where is the pod eviction code implemented in the Kubernetes source? | `pkg/controller/nodelifecycle/node_lifecycle_controller.go` | No |
| 2 | Where is the Kubernetes scheduler entry point defined? | `cmd/kube-scheduler/scheduler.go`, `pkg/scheduler/scheduler.go` | No |
| 3 | Which component talks to the container runtime and how does it do it? | `pkg/kubelet/kubelet.go`, `pkg/kubelet/kuberuntime/kuberuntime_manager.go` | Yes |
| 4 | Where is the API server request handler and routing implemented? | `staging/src/k8s.io/apiserver/pkg/server/genericapiserver.go`, `pkg/registry/` | Yes |
| 5 | How does the kubelet start and manage pod lifecycle on a node? | `pkg/kubelet/kubelet.go`, `pkg/kubelet/pod_workers.go` | Yes |
| 6 | Where are the built-in Kubernetes controllers (Deployment, ReplicaSet, etc.) implemented? | `pkg/controller/deployment/`, `pkg/controller/replicaset/` | No |
| 7 | How does the scheduler score nodes and select the best one for a pod? | `pkg/scheduler/framework/interface.go`, `pkg/scheduler/framework/plugins/` | Yes |
| 8 | Why would a pod stay in Pending state and where in the code is this enforced? | `pkg/scheduler/scheduler.go`, `pkg/scheduler/framework/plugins/noderesources/` | Yes |
| 9 | How does Kubernetes detect a node failure and reschedule its pods? | `pkg/controller/nodelifecycle/node_lifecycle_controller.go`, `pkg/controller/util/node/controller_utils.go` | Yes |
| 10 | What is the current cost per 1 000 tokens for Gemini Flash versus GPT-4o as of today? | Cannot be answered from the Kubernetes source code — requires live pricing data from provider websites | No |
